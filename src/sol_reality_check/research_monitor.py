"""Pre-registered, append-only directional forecasts and their honest forward scorecard."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from sol_reality_check.config import ROOT
from sol_reality_check.ledger import read_jsonl
from sol_reality_check.predictive_monitor import append_immutable, first_publications
from sol_reality_check.research_archive import (
    ensure_baseline,
    verify_collected_history,
    verify_run_archives,
)
from sol_reality_check.utils import iso_z, payload_hash, utc_now, write_json

PHASES = ["prospective", "reconstructed"]


def timestamp(value: Any) -> pd.Timestamp:
    return pd.Timestamp(value).tz_convert("UTC")


def finite(value: Any) -> float | None:
    try:
        result = float(value)
        return result if np.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def load_protocol(root: Path) -> dict[str, Any]:
    return json.loads((root / "config/research_protocol.json").read_text())


def prediction_sources(root: Path) -> list[dict[str, Any]]:
    """Retain an earlier research publication when a parallel live run shares its ID."""
    return read_jsonl(root / "data/ledger/predictions.jsonl") + read_jsonl(
        root / "data/research/parallel_predictions.jsonl"
    )


def research_rows(root: Path) -> list[dict[str, Any]]:
    path = root / "data/curated/signaalonderzoek.parquet"
    if not path.exists():
        return []
    frame = pd.read_parquet(path)
    frame = frame[frame["mode"].eq("production")].sort_values("run_at_utc")
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def build_inputs(
    root: Path, protocol: dict[str, Any], now: str
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    predictions = first_publications(
        [
            row
            for row in prediction_sources(root)
            if timestamp(row["created_at_utc"]) <= timestamp(now)
        ]
    )
    research = [
        row for row in research_rows(root) if timestamp(row["run_at_utc"]) <= timestamp(now)
    ]
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in research:
        by_date.setdefault(str(row["data_cutoff_utc"])[:10], []).append(row)
    prices: dict[str, dict[str, Any]] = {}
    rows = []
    for prediction in predictions:
        day = prediction["data_cutoff_utc"][:10]
        published = prediction["created_at_utc"]
        candidates = by_date.get(day, [])
        available = [r for r in candidates if timestamp(r["run_at_utc"]) <= timestamp(published)]
        component = available[0] if available else {}
        btc_source = candidates[0] if candidates else {}
        prices[day] = {
            "sol": finite(prediction["feature_snapshot"].get("sol_close")),
            "sol_available_at": published,
            "btc": finite(btc_source.get("btc_price")),
            "btc_available_at": btc_source.get("run_at_utc"),
            "source_prediction_id": prediction["prediction_id"],
        }
        day_ts = pd.Timestamp(day)
        rows.append(
            {
                "date": day,
                "published_at_utc": published,
                "prediction_id": prediction["prediction_id"],
                "prediction_sha256": prediction["payload_sha256"],
                "method_version": prediction["method_version"],
                "quality": finite(prediction.get("evidence_quality")),
                "score": finite(prediction.get("market_signal")),
                "sol": prices[day]["sol"],
                "btc": finite(component.get("btc_price")),
                "network": finite(component.get("network_usage_score")),
                "components_at_utc": component.get("run_at_utc"),
                "time_days": (day_ts - pd.Timestamp("2026-07-04")).days,
                **{f"weekday_{i}": float(day_ts.dayofweek == i) for i in range(1, 7)},
            }
        )
    if not rows:
        return pd.DataFrame(), prices
    frame = pd.DataFrame(rows).set_index("date")
    calendar = pd.date_range(frame.index.min(), frame.index.max()).strftime("%Y-%m-%d")
    frame = frame.reindex(calendar)
    frame.index.name = "date"
    high = (frame.quality > protocol["high_quality_threshold"]).where(frame.quality.notna())
    starts = (high.eq(True) & high.shift(1).eq(False)).astype(float)
    starts = starts.where(high.notna() & high.shift(1).notna())
    counts = starts.rolling(protocol["episode_window_days"]).sum()
    difference = counts - counts.shift(protocol["episode_comparison_lag_days"])
    frame["blue_occupancy_14"] = (
        high.astype(float).rolling(protocol["occupancy_window_days"]).mean()
    )
    frame["blue_blocks_10"] = counts
    frame["blue_blocks_delta7"] = difference
    frame["blue_blocks_falling"] = (difference < 0).astype(float).where(difference.notna())
    frame["network_below_50"] = (
        (frame.network < protocol["network_threshold"]).astype(float).where(frame.network.notna())
    )
    for asset in ["sol", "btc"]:
        frame[f"{asset}_momentum_7"] = frame[asset] / frame[asset].shift(7) - 1
    return frame, prices


def close_at(day: str) -> pd.Timestamp:
    return pd.Timestamp(day, tz="UTC") + pd.Timedelta(days=1)


def observed_return(
    prices: dict[str, dict[str, Any]], entry: str, exit_day: str, asset: str, known_at: str
) -> float | None:
    a, b = prices.get(entry, {}), prices.get(exit_day, {})
    for row in [a, b]:
        if finite(row.get(asset)) is None or not row.get(f"{asset}_available_at"):
            return None
        if timestamp(row[f"{asset}_available_at"]) >= timestamp(known_at):
            return None
    if a[asset] <= 0:
        return None
    return float(b[asset] / a[asset] - 1)


def train_forecasts(
    frame: pd.DataFrame,
    prices: dict[str, dict[str, Any]],
    row: pd.Series,
    horizon: int,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    config = protocol["model"]
    baseline = config["baseline_features"]
    extras = [c["feature"] for c in protocol["candidates"]]
    columns = baseline + extras
    if any(finite(row.get(column)) is None for column in columns):
        return {"available": False, "reason": "Onvolledige invoer bij eerste publicatie."}
    candidates = frame[(frame.index < row.name) & frame.method_version.eq(row.method_version)]
    training = []
    for day, previous in candidates.dropna(subset=columns).iterrows():
        entry = timestamp(previous.published_at_utc).date().isoformat()
        exit_day = (pd.Timestamp(entry) + pd.Timedelta(days=horizon)).date().isoformat()
        if close_at(exit_day) >= timestamp(row.published_at_utc):
            continue
        outcome = observed_return(prices, entry, exit_day, "sol", row.published_at_utc)
        if outcome is not None:
            training.append((day, previous, outcome, exit_day))
    training = training[-config["training_rows"] :]
    if len(training) < config["minimum_training_rows"]:
        return {
            "available": False,
            "reason": "Nog minder dan 45 volledig bekende trainingsrijen.",
            "training_n": len(training),
        }
    target = np.array([int(result > 0) for _, _, result, _ in training])
    if len(set(target)) < 2:
        return {"available": False, "reason": "Trainingsperiode bevat slechts één richting."}
    x = pd.DataFrame([previous[columns] for _, previous, _, _ in training], columns=columns)
    test = pd.DataFrame([row[columns]], columns=columns)
    result: dict[str, Any] = {
        "available": True,
        "training_n": len(training),
        "training_prediction_ids": [p.prediction_id for _, p, _, _ in training],
        "training_last_exit_date": max(exit_day for _, _, _, exit_day in training),
        "training_known_before_utc": row.published_at_utc,
        "sklearn_version": sklearn.__version__,
        "models": {},
    }
    groups = {"baseline": baseline} | {
        c["candidate_id"]: baseline + [c["feature"]] for c in protocol["candidates"]
    }
    for name, fields in groups.items():
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=config["C"], solver="lbfgs", max_iter=2000, tol=1e-10, random_state=0
            ),
        )
        model.fit(x[fields], target)
        scaler = model.named_steps["standardscaler"]
        logistic = model.named_steps["logisticregression"]
        result["models"][name] = {
            "probability_up": float(model.predict_proba(test[fields])[0, 1]),
            "features": fields,
            "mean": scaler.mean_.tolist(),
            "scale": scaler.scale_.tolist(),
            "coefficients": logistic.coef_[0].tolist(),
            "intercept": float(logistic.intercept_[0]),
        }
    return result


def register_forecasts(
    root: Path,
    protocol: dict[str, Any],
    frame: pd.DataFrame,
    prices: dict[str, dict[str, Any]],
    now: str,
) -> None:
    path = root / "data/research/forecasts.jsonl"
    existing = {r["forecast_id"] for r in read_jsonl(path)}
    protocol_hash = payload_hash(protocol)
    for day, row in frame[frame.prediction_id.notna()].iterrows():
        entry = timestamp(row.published_at_utc).date().isoformat()
        prospective = timestamp(row.published_at_utc) >= timestamp(
            protocol["locked_at_utc"]
        ) and timestamp(now) < close_at(entry)
        for horizon in protocol["horizons_days"]:
            keys = {
                c["candidate_id"]: f"{protocol['protocol_id']}__{c['candidate_id']}"
                f"__{row.prediction_id}__{horizon}d"
                for c in protocol["candidates"]
            }
            if all(key in existing for key in keys.values()):
                continue
            trained = train_forecasts(frame, prices, row, horizon, protocol)
            exit_day = (pd.Timestamp(entry) + pd.Timedelta(days=horizon)).date().isoformat()
            features = {c["feature"]: finite(row.get(c["feature"])) for c in protocol["candidates"]}
            for candidate in protocol["candidates"]:
                key = keys[candidate["candidate_id"]]
                if key in existing:
                    continue
                model = trained.get("models", {}).get(candidate["candidate_id"], {})
                baseline = trained.get("models", {}).get("baseline", {})
                probability = model.get("probability_up")
                value = features[candidate["feature"]]
                active = None if candidate["unit"] == "fraction" or value is None else bool(value)
                record = {
                    "forecast_id": key,
                    "protocol_id": protocol["protocol_id"],
                    "protocol_sha256": protocol_hash,
                    "candidate_id": candidate["candidate_id"],
                    "date": day,
                    "published_at_utc": row.published_at_utc,
                    "recorded_at_utc": now,
                    "phase": "prospective" if prospective else "reconstructed",
                    "source_prediction_id": row.prediction_id,
                    "source_prediction_sha256": row.prediction_sha256,
                    "method_version": row.method_version,
                    "components_at_utc": row.components_at_utc
                    if pd.notna(row.components_at_utc)
                    else None,
                    "feature_value": value,
                    "feature_snapshot": features,
                    "baseline_inputs": {
                        field: finite(row.get(field))
                        for field in protocol["model"]["baseline_features"]
                    },
                    "active": active,
                    "rule_direction": "down" if active else None,
                    "horizon_days": horizon,
                    "entry_date": entry,
                    "exit_date": exit_day,
                    "entry_after_utc": iso_z(close_at(entry).to_pydatetime()),
                    "outcome_after_utc": iso_z(close_at(exit_day).to_pydatetime()),
                    "model_available": trained["available"],
                    "unavailable_reason": trained.get("reason"),
                    "probability_up": probability,
                    "baseline_probability_up": baseline.get("probability_up"),
                    "predicted_direction": ("up" if probability >= 0.5 else "down")
                    if probability is not None
                    else None,
                    "training_receipt": {k: v for k, v in trained.items() if k != "models"},
                    "model_receipt": model,
                    "baseline_receipt": baseline,
                }
                append_immutable(path, record, ["forecast_id"])


def settle_outcomes(
    root: Path, forecasts: list[dict[str, Any]], prices: dict[str, dict[str, Any]], now: str
) -> None:
    path = root / "data/research/outcomes.jsonl"
    existing = {r["forecast_id"] for r in read_jsonl(path)}
    for row in forecasts:
        if row["forecast_id"] in existing or timestamp(now) <= close_at(row["exit_date"]):
            continue
        sol = observed_return(prices, row["entry_date"], row["exit_date"], "sol", now)
        btc = observed_return(prices, row["entry_date"], row["exit_date"], "btc", now)
        if sol is None or btc is None:
            continue
        actual = int(sol > 0)
        probability, baseline = row["probability_up"], row["baseline_probability_up"]
        append_immutable(
            path,
            {
                "forecast_id": row["forecast_id"],
                "forecast_sha256": row["payload_sha256"],
                "settled_at_utc": now,
                "horizon_days": row["horizon_days"],
                "sol_return": sol,
                "btc_return": btc,
                "relative_return": sol - btc,
                "actual_direction": "up" if sol > 0 else "down" if sol < 0 else "flat",
                "brier": (probability - actual) ** 2 if probability is not None else None,
                "baseline_brier": (baseline - actual) ** 2 if baseline is not None else None,
                "entry_prices": prices[row["entry_date"]],
                "exit_prices": prices[row["exit_date"]],
            },
            ["forecast_id"],
        )


def nonoverlap(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    previous_end = ""
    for row in sorted(rows, key=lambda r: r["entry_date"]):
        if row["entry_date"] >= previous_end:
            chosen.append(row)
            previous_end = row["exit_date"]
    return chosen


def paired_interval(rows: list[dict[str, Any]], horizon: int) -> list[float | None]:
    if len(rows) < 20 or len(nonoverlap(rows)) < 3:
        return [None, None]
    values = np.array([r["baseline_brier"] - r["brier"] for r in rows])
    block = max(7, horizon)
    rng = np.random.default_rng(20261109)
    starts = rng.integers(0, len(values), (2000, int(np.ceil(len(values) / block))))
    indices = ((starts[:, :, None] + np.arange(block)) % len(values)).reshape(2000, -1)
    samples = values[indices[:, : len(values)]].mean(axis=1)
    return [float(x) for x in np.quantile(samples, [0.025, 0.975])]


def summarize(rows: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
    matured = [r for r in rows if r.get("sol_return") is not None]
    scored = [r for r in matured if r.get("brier") is not None]
    up = [r for r in scored if r["sol_return"] > 0]
    down = [r for r in scored if r["sol_return"] < 0]
    up_correct = sum(r["predicted_direction"] == "up" for r in up)
    down_correct = sum(r["predicted_direction"] == "down" for r in down)
    up_recall = up_correct / len(up) if up else None
    down_recall = down_correct / len(down) if down else None
    active = [r for r in matured if r["active"] is True]
    inactive = [r for r in matured if r["active"] is False]

    def mean(group: list[dict[str, Any]], field: str) -> float | None:
        return float(np.mean([r[field] for r in group])) if group else None

    bins = []
    for low, high in [(0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.00001)]:
        selected = [r for r in scored if low <= r["probability_up"] < high]
        bins.append(
            {
                "from": low,
                "through": min(high, 1),
                "n": len(selected),
                "predicted": mean(selected, "probability_up"),
                "observed": float(np.mean([r["sol_return"] > 0 for r in selected]))
                if selected
                else None,
            }
        )
    active_mean, inactive_mean = mean(active, "sol_return"), mean(inactive, "sol_return")
    return {
        "registered_n": len(rows),
        "matured_n": len(matured),
        "pending_n": len(rows) - len(matured),
        "scored_n": len(scored),
        "unscored_matured_n": len(matured) - len(scored),
        "nonoverlap_n": len(nonoverlap(scored)),
        "actual_up_n": len(up),
        "actual_down_n": len(down),
        "up_correct_n": up_correct,
        "down_correct_n": down_correct,
        "up_recall": up_recall,
        "down_recall": down_recall,
        "balanced_accuracy": (up_recall + down_recall) / 2
        if up_recall is not None and down_recall is not None
        else None,
        "accuracy": (up_correct + down_correct) / len(scored) if scored else None,
        "brier": mean(scored, "brier"),
        "baseline_brier": mean(scored, "baseline_brier"),
        "brier_improvement": float(np.mean([r["baseline_brier"] - r["brier"] for r in scored]))
        if scored
        else None,
        "brier_improvement_ci95": paired_interval(scored, horizon),
        "coinflip_brier": 0.25 if scored else None,
        "always_up_brier": 1 - len(up) / len(scored) if scored else None,
        "always_down_brier": len(up) / len(scored) if scored else None,
        "calibration": bins,
        "active_n": len(active),
        "active_nonoverlap_n": len(nonoverlap(active)),
        "active_negative_n": sum(r["sol_return"] < 0 for r in active),
        "active_mean_sol": active_mean,
        "inactive_n": len(inactive),
        "inactive_mean_sol": inactive_mean,
        "active_mean_relative": mean(active, "relative_return"),
        "active_uplift": active_mean - inactive_mean
        if active_mean is not None and inactive_mean is not None
        else None,
    }


def validate_research_ledgers(root: Path) -> None:
    definitions = read_jsonl(root / "data/research/definitions.jsonl")
    forecasts = read_jsonl(root / "data/research/forecasts.jsonl")
    outcomes = read_jsonl(root / "data/research/outcomes.jsonl")
    protocols = {r["protocol_id"]: r for r in definitions}
    forecast_map = {r["forecast_id"]: r for r in forecasts}
    sources = prediction_sources(root)
    if any(row.get("payload_sha256") != payload_hash(row) for row in sources):
        raise ValueError("Research prediction source hash mismatch")
    known_sources = {(r["prediction_id"], r["payload_sha256"]) for r in sources}
    for rows, key in [
        (definitions, "protocol_id"),
        (forecasts, "forecast_id"),
        (outcomes, "forecast_id"),
    ]:
        if len({r[key] for r in rows}) != len(rows):
            raise ValueError(f"Duplicate research {key}")
        if any(r.get("payload_sha256") != payload_hash(r) for r in rows):
            raise ValueError("Research ledger hash mismatch")
    for row in forecasts:
        if (row["source_prediction_id"], row["source_prediction_sha256"]) not in known_sources:
            raise ValueError("Research forecast lost its original prediction source")
        protocol = protocols.get(row["protocol_id"])
        if not protocol or row["protocol_sha256"] != payload_hash(protocol):
            raise ValueError("Research forecast references changed or missing protocol")
        if row["phase"] == "prospective" and not (
            timestamp(row["published_at_utc"]) >= timestamp(protocol["locked_at_utc"])
            and timestamp(row["published_at_utc"])
            <= timestamp(row["recorded_at_utc"])
            < close_at(row["entry_date"])
        ):
            raise ValueError("Late forecast cannot be prospective")
        receipt = row.get("training_receipt", {})
        if row["model_available"] and close_at(receipt["training_last_exit_date"]) >= timestamp(
            row["published_at_utc"]
        ):
            raise ValueError("Training outcome leaks into forecast")
        for field in ["probability_up", "baseline_probability_up"]:
            if row[field] is not None and not 0 <= row[field] <= 1:
                raise ValueError("Invalid forecast probability")
    for row in outcomes:
        forecast = forecast_map.get(row["forecast_id"])
        if not forecast or row["forecast_sha256"] != forecast["payload_sha256"]:
            raise ValueError("Outcome without intact forecast")
        for asset in ["sol", "btc"]:
            computed = row["exit_prices"][asset] / row["entry_prices"][asset] - 1
            if abs(computed - row[f"{asset}_return"]) > 1e-12:
                raise ValueError("Research return differs from endpoint prices")
    shadow_definitions = read_jsonl(root / "data/research/shadow_definitions.jsonl")
    shadow_rows = read_jsonl(root / "data/research/shadow_quality.jsonl")
    known_shadow = {r["definition_id"] for r in shadow_definitions}
    if len(known_shadow) != len(shadow_definitions):
        raise ValueError("Duplicate shadow definition")
    seen = set()
    for row in shadow_definitions + shadow_rows:
        if row.get("payload_sha256") != payload_hash(row):
            raise ValueError("Shadow quality hash mismatch")
    for row in shadow_rows:
        shadow_key = (row["definition_id"], row["run_at_utc"])
        if row["definition_id"] not in known_shadow or shadow_key in seen:
            raise ValueError("Shadow quality references unknown or duplicate definition")
        seen.add(shadow_key)


def generate_research_monitor(root: Path = ROOT, now: datetime | None = None) -> dict[str, Any]:
    recorded_at = iso_z(now or utc_now())
    manifest = ensure_baseline(root)
    protocol = load_protocol(root)
    definitions_path = root / "data/research/definitions.jsonl"
    append_immutable(definitions_path, protocol, ["protocol_id"])
    frame, prices = build_inputs(root, protocol, recorded_at)
    if not frame.empty:
        register_forecasts(root, protocol, frame, prices, recorded_at)
    forecasts = read_jsonl(root / "data/research/forecasts.jsonl")
    settle_outcomes(root, forecasts, prices, recorded_at)
    outcomes = read_jsonl(root / "data/research/outcomes.jsonl")
    validate_research_ledgers(root)
    verify_collected_history(root)
    verify_run_archives(root)
    outcome_map = {r["forecast_id"]: r for r in outcomes}
    joined = [
        row | outcome_map.get(row["forecast_id"], {})
        for row in forecasts
        if row["protocol_id"] == protocol["protocol_id"]
    ]
    candidates = []
    for candidate in protocol["candidates"]:
        selected = [r for r in joined if r["candidate_id"] == candidate["candidate_id"]]
        latest = sorted([r for r in selected if r["horizon_days"] == 7], key=lambda r: r["date"])[
            -1:
        ]
        candidates.append(
            candidate
            | {
                "latest": public_record(latest[0]) if latest else None,
                "evaluations": [
                    {
                        "phase": phase,
                        "horizon_days": horizon,
                        **summarize(
                            [
                                r
                                for r in selected
                                if r["phase"] == phase and r["horizon_days"] == horizon
                            ],
                            horizon,
                        ),
                    }
                    for phase in PHASES
                    for horizon in protocol["horizons_days"]
                ],
            }
        )
    shadow = read_jsonl(root / "data/research/shadow_quality.jsonl")
    downloads = []
    for name in [
        "definitions.jsonl",
        "forecasts.jsonl",
        "outcomes.jsonl",
        "parallel_predictions.jsonl",
        "shadow_definitions.jsonl",
        "shadow_quality.jsonl",
    ]:
        source = root / "data/research" / name
        if not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("")
        (root / "site/data" / f"research_{name}").write_bytes(source.read_bytes())
        downloads.append({"name": name, "path": f"./data/research_{name}"})
    (root / "site/data/research_baseline.tar.gz").write_bytes(
        (root / "data/research/baseline/collected-data.tar.gz").read_bytes()
    )
    write_json(root / "site/data/research_baseline_manifest.json", manifest)
    payload = {
        "schema_version": "1.0",
        "name": "Gericht voorspelonderzoek",
        "generated_at_utc": recorded_at,
        "data_cutoff": frame.index.max() if not frame.empty else None,
        "protocol": protocol,
        "candidates": candidates,
        "records": [public_record(r) for r in joined],
        "weekday_diagnostics": weekday_diagnostics(frame),
        "shadow_quality": [
            {k: v for k, v in r.items() if k != "evaluation"}
            | {"evaluation": {k: v for k, v in r["evaluation"].items() if k != "test_rows"}}
            for r in shadow
        ],
        "baseline_archive": {
            "file_count": manifest["file_count"],
            "sha256": manifest["archive_sha256"],
            "archive_path": "./data/research_baseline.tar.gz",
            "manifest_path": "./data/research_baseline_manifest.json",
            "verified": True,
        },
        "downloads": downloads,
        "source_policy": (
            "Eerste vastgelegde prediction per datadag, inclusief bewaarde parallelle "
            "publicaties. Bron-ID én bronhash identificeren de oorspronkelijke versie. "
            "De live prediction-ledger blijft ongewijzigd; geen prijsinterpolatie."
        ),
        "limitations": [
            "Experimentele modelkansen zijn nog niet prospectief gevalideerd.",
            "Dagelijkse weekuitkomsten overlappen. Het aantal losse vensters staat apart.",
            "Historische reconstructies zijn gekozen met kennis van de onderzoeksperiode.",
            "Een hoger succespercentage in een dalende markt is op zichzelf geen meerwaarde.",
            protocol["cost_policy"],
        ],
    }
    write_json(root / "site/data/research_monitor.json", payload)
    return payload


def public_record(row: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "forecast_id",
        "candidate_id",
        "date",
        "published_at_utc",
        "recorded_at_utc",
        "phase",
        "method_version",
        "feature_value",
        "active",
        "rule_direction",
        "horizon_days",
        "entry_date",
        "exit_date",
        "outcome_after_utc",
        "model_available",
        "unavailable_reason",
        "probability_up",
        "baseline_probability_up",
        "predicted_direction",
        "sol_return",
        "btc_return",
        "relative_return",
        "brier",
        "baseline_brier",
        "actual_direction",
        "settled_at_utc",
    ]
    return {field: row.get(field) for field in fields}


def weekday_diagnostics(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    labels = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
    return [
        {"weekday": label, "n": len(part), "capped_n": int(part.quality.eq(55).sum())}
        for i, label in enumerate(labels)
        if not (part := frame[pd.to_datetime(frame.index).dayofweek == i]).empty
    ]
