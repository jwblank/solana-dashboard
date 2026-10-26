from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sol_reality_check.config import ROOT
from sol_reality_check.ledger import read_jsonl, with_hash
from sol_reality_check.utils import canonical_json, write_json

HORIZONS = [1, 3, 7, 14, 30]
PRIMARY_HORIZON = 7
DEFINITION_ID = "peak-density-v1"
LOCKED_AT_UTC = "2026-10-26T10:55:00Z"

SIGNAL_DEFINITION: dict[str, Any] = {
    "definition_id": DEFINITION_ID,
    "candidate_name": "Dichtheid van bevestigde scorepieken",
    "version": "1.0.0",
    "status": "locked",
    "locked_at_utc": LOCKED_AT_UTC,
    "discovery_period": {
        "from": "2026-07-04",
        "through": "2026-10-24",
        "classification": "retrospective_exploratory",
    },
    "prospective_policy": (
        "Een event is prospectief wanneer de eerste officiële publicatie op of na "
        f"{LOCKED_AT_UTC} plaatsvindt. Historische backfill blijft altijd retrospectief."
    ),
    "input_policy": "Alleen de eerste officiële prediction per data_cutoff-dag.",
    "peak_rule": (
        "Op dag t wordt t-1 als piek bevestigd wanneer score[t-1] > score[t-2] "
        "en score[t-1] >= score[t]."
    ),
    "feature": {
        "name": "confirmed_peak_count_10d",
        "window_observations": 10,
        "threshold": 3,
        "operator": ">=",
    },
    "event_rule": (
        "Start een event wanneer het aantal bevestigde pieken in de laatste tien "
        "officiële signalen van minder dan drie naar ten minste drie gaat."
    ),
    "cooldown_days": 10,
    "primary_horizon_days": PRIMARY_HORIZON,
    "secondary_horizons_days": [1, 3, 14, 30],
    "control_policy": (
        "Alle volwassen officiële dagvensters met minder dan drie bevestigde pieken "
        "in dezelfde 10-daagse feature. Overlap wordt expliciet gemeld; inferentie is "
        "geclusterd op onafhankelijke events."
    ),
    "confirmation_thresholds": {
        "provisionally_confirmed": {
            "minimum_prospective_events": 20,
            "sol_uplift_ci_lower_above_zero": True,
            "early_late_direction_stable": True,
        },
        "robust": {
            "minimum_prospective_events": 40,
            "btc_relative_ci_lower_above_zero": True,
            "multiple_regimes": True,
        },
    },
    "change_policy": (
        "Een wijziging in feature, drempel, horizon, cooldown of controlegroep vereist "
        "een nieuwe definition_id en versie; bestaande records worden nooit herschreven."
    ),
    "economic_relevance_threshold": {
        "sol_uplift_7d_percentage_points": 2.0,
        "note": "Apart van statistische bevestiging beoordeeld.",
    },
    "discovery_note": (
        "De kandidaat is na inspectie van historische patronen gekozen. De bestaande "
        "uitkomsten zijn daarom uitsluitend verkennend en tellen niet als bevestiging."
    ),
}


def generate_predictive_monitor(root: Path = ROOT) -> dict[str, Any]:
    """Append immutable signal records and publish a reproducible monitor payload."""
    definition_path = root / "data" / "ledger" / "signal_definitions.jsonl"
    event_path = root / "data" / "ledger" / "signal_events.jsonl"
    outcome_path = root / "data" / "ledger" / "signal_outcomes.jsonl"
    prediction_path = root / "data" / "ledger" / "predictions.jsonl"
    research_path = root / "data" / "curated" / "signaalonderzoek.parquet"

    append_immutable(definition_path, SIGNAL_DEFINITION, ["definition_id"])
    raw_predictions = read_jsonl(prediction_path)
    predictions = first_publications(raw_predictions)
    research = read_research(research_path)
    signal_frame = build_signal_frame(predictions)
    research_by_date = first_research_publications(research)

    for event in derive_events(signal_frame, research_by_date):
        append_immutable(event_path, event, ["event_id"])

    events = read_jsonl(event_path)
    for outcome in derive_outcomes(events, signal_frame, research_by_date):
        append_immutable(outcome_path, outcome, ["event_id", "horizon_days"])

    definitions = read_jsonl(definition_path)
    outcomes = read_jsonl(outcome_path)
    validate_signal_ledgers(definitions, events, outcomes)
    publish_ledger_copies(root, [definition_path, event_path, outcome_path])
    payload = build_monitor_payload(
        definitions=definitions,
        events=events,
        outcomes=outcomes,
        signal_frame=signal_frame,
        research=research,
        research_by_date=research_by_date,
        raw_prediction_count=len(raw_predictions),
        source_paths={
            "predictions": prediction_path,
            "research": research_path,
            "definitions": definition_path,
            "events": event_path,
            "outcomes": outcome_path,
        },
    )
    write_json(root / "site" / "data" / "predictive_monitor.json", payload)
    return payload


def append_immutable(path: Path, payload: dict[str, Any], key_fields: list[str]) -> bool:
    """Append once; reject a changed payload for an already registered key."""
    path.parent.mkdir(parents=True, exist_ok=True)
    key = tuple(payload.get(field) for field in key_fields)
    for row in read_jsonl(path):
        row_key = tuple(row.get(field) for field in key_fields)
        if row_key != key:
            continue
        existing = {name: value for name, value in row.items() if name != "payload_sha256"}
        if canonical_json(existing) != canonical_json(payload):
            raise ValueError(
                f"Immutable ledger conflict in {path} for "
                + ", ".join(
                    f"{field}={value}"
                    for field, value in zip(key_fields, key, strict=False)
                )
            )
        return False
    row = with_hash(payload)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        )
    return True


def first_publications(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: str(row.get("created_at_utc") or ""))
    first: dict[str, dict[str, Any]] = {}
    for row in ordered:
        date = str(row.get("data_cutoff_utc") or "")[:10]
        if date and date not in first:
            first[date] = row
    return [first[date] for date in sorted(first)]


def read_research(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path).sort_values("run_at_utc").reset_index(drop=True)


def first_research_publications(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if frame.empty:
        return {}
    ordered = frame.sort_values("run_at_utc")
    result: dict[str, dict[str, Any]] = {}
    for _, row in ordered.iterrows():
        date = str(row.get("data_cutoff_utc") or "")[:10]
        if date and date not in result:
            result[date] = {
                "run_at_utc": clean_value(row.get("run_at_utc")),
                "btc_price": clean_number(row.get("btc_price")),
                "realized_volatility_30d": clean_number(
                    row.get("realized_volatility_30d")
                ),
                "btc_return_7d": clean_number(row.get("btc_return_7d")),
                "method_version": clean_value(row.get("method_version")),
            }
    return result


def build_signal_frame(predictions: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for prediction in predictions:
        date = str(prediction.get("data_cutoff_utc") or "")[:10]
        score = clean_number(prediction.get("market_signal"))
        sol_price = clean_number((prediction.get("feature_snapshot") or {}).get("sol_close"))
        if not date or score is None or sol_price is None:
            continue
        rows.append(
            {
                "date": date,
                "created_at_utc": prediction.get("created_at_utc"),
                "prediction_id": prediction.get("prediction_id"),
                "prediction_sha256": prediction.get("payload_sha256"),
                "method_version": prediction.get("method_version"),
                "regime": prediction.get("regime"),
                "score": score,
                "sol_price": sol_price,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.sort_values("date").reset_index(drop=True)
    frame["confirmed_peak"] = (frame["score"].shift(1) > frame["score"].shift(2)) & (
        frame["score"].shift(1) >= frame["score"]
    )
    rolling_peaks = frame["confirmed_peak"].rolling(10, min_periods=10).sum()
    frame["feature_ready"] = rolling_peaks.notna()
    frame["peak_count_10d"] = rolling_peaks.fillna(0).astype(int)
    frame["threshold_crossing"] = (frame["peak_count_10d"] >= 3) & (
        frame["peak_count_10d"].shift(1).fillna(0) < 3
    )
    return frame


def derive_events(
    frame: pd.DataFrame, research_by_date: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    events: list[dict[str, Any]] = []
    last_event_date: pd.Timestamp | None = None
    for _, row in frame[frame["threshold_crossing"]].iterrows():
        date = pd.Timestamp(row["date"])
        if last_event_date is not None and (date - last_event_date).days < 10:
            continue
        last_event_date = date
        date_text = date.date().isoformat()
        research = research_by_date.get(date_text, {})
        created_at = str(row["created_at_utc"])
        phase = "prospective" if created_at >= LOCKED_AT_UTC else "retrospective"
        event = {
            "event_id": f"{DEFINITION_ID}__{date_text}",
            "definition_id": DEFINITION_ID,
            "definition_version": SIGNAL_DEFINITION["version"],
            "event_date": date_text,
            "first_published_at_utc": created_at,
            "evaluation_phase": phase,
            "registration_status": (
                "prospective_registered" if phase == "prospective" else "historical_backfill"
            ),
            "source_prediction_id": row["prediction_id"],
            "source_prediction_sha256": row["prediction_sha256"],
            "method_version": row["method_version"],
            "regime": row["regime"],
            "feature_name": "confirmed_peak_count_10d",
            "feature_value": int(row["peak_count_10d"]),
            "threshold": 3,
            "cooldown_days": 10,
            "sol_entry_price": rounded(row["sol_price"], 8),
            "btc_entry_price": rounded(research.get("btc_price"), 8),
            "context_at_entry": {
                "realized_volatility_30d": rounded(
                    research.get("realized_volatility_30d"), 8
                ),
                "btc_return_7d": rounded(research.get("btc_return_7d"), 8),
                "btc_source_run_at_utc": research.get("run_at_utc"),
            },
            "maturity_dates": {
                f"{horizon}d": (date + pd.Timedelta(days=horizon)).date().isoformat()
                for horizon in HORIZONS
            },
        }
        events.append(event)
    return events


def derive_outcomes(
    events: list[dict[str, Any]],
    frame: pd.DataFrame,
    research_by_date: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    prices = {str(row["date"]): row for _, row in frame.iterrows()}
    outcomes: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda row: str(row.get("event_date"))):
        entry_sol = clean_number(event.get("sol_entry_price"))
        entry_btc = clean_number(event.get("btc_entry_price"))
        if entry_sol is None:
            continue
        for horizon in HORIZONS:
            maturity_date = (pd.Timestamp(event["event_date"]) + pd.Timedelta(days=horizon))
            maturity_text = maturity_date.date().isoformat()
            exit_row = prices.get(maturity_text)
            if exit_row is None:
                continue
            exit_sol = clean_number(exit_row.get("sol_price"))
            exit_btc = clean_number(research_by_date.get(maturity_text, {}).get("btc_price"))
            sol_return = return_value(entry_sol, exit_sol)
            btc_return = return_value(entry_btc, exit_btc)
            relative = (
                None if sol_return is None or btc_return is None else sol_return - btc_return
            )
            outcomes.append(
                {
                    "outcome_id": f"{event['event_id']}__{horizon}d",
                    "event_id": event["event_id"],
                    "definition_id": event["definition_id"],
                    "definition_version": event["definition_version"],
                    "evaluation_phase": event["evaluation_phase"],
                    "horizon_days": horizon,
                    "is_primary_horizon": horizon == PRIMARY_HORIZON,
                    "maturity_date": maturity_text,
                    "observed_at_utc": exit_row.get("created_at_utc"),
                    "source_prediction_id": exit_row.get("prediction_id"),
                    "source_prediction_sha256": exit_row.get("prediction_sha256"),
                    "sol_entry_price": rounded(entry_sol, 8),
                    "sol_exit_price": rounded(exit_sol, 8),
                    "btc_entry_price": rounded(entry_btc, 8),
                    "btc_exit_price": rounded(exit_btc, 8),
                    "sol_return": rounded(sol_return, 10),
                    "btc_return": rounded(btc_return, 10),
                    "btc_relative_return": rounded(relative, 10),
                    "direction_positive": None if sol_return is None else sol_return > 0,
                    "status": "observed",
                }
            )
    return outcomes


def validate_signal_ledgers(
    definitions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> None:
    validate_unique_hashes(definitions, ["definition_id"], "definition")
    validate_unique_hashes(events, ["event_id"], "event")
    validate_unique_hashes(outcomes, ["event_id", "horizon_days"], "outcome")
    definition_ids = {row.get("definition_id") for row in definitions}
    event_ids = {row.get("event_id") for row in events}
    for event in events:
        if event.get("definition_id") not in definition_ids:
            raise ValueError(f"Event without definition: {event.get('event_id')}")
    for outcome in outcomes:
        if outcome.get("event_id") not in event_ids:
            raise ValueError(f"Outcome without event: {outcome.get('outcome_id')}")


def validate_unique_hashes(
    rows: list[dict[str, Any]], key_fields: list[str], label: str
) -> None:
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = tuple(row.get(field) for field in key_fields)
        if key in seen:
            raise ValueError(f"Duplicate {label} ledger key: {key}")
        seen.add(key)
        expected = with_hash({k: v for k, v in row.items() if k != "payload_sha256"})
        if row.get("payload_sha256") != expected["payload_sha256"]:
            raise ValueError(f"Invalid {label} payload hash: {key}")


def build_monitor_payload(
    *,
    definitions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    signal_frame: pd.DataFrame,
    research: pd.DataFrame,
    research_by_date: dict[str, dict[str, Any]],
    raw_prediction_count: int,
    source_paths: dict[str, Path],
) -> dict[str, Any]:
    controls = control_observations(signal_frame, research_by_date)
    event_rows = event_view(events, outcomes)
    primary_metrics = build_primary_metrics(events, outcomes, controls)
    status = evaluate_status(events, outcomes, controls, primary_metrics)
    latest_source = latest_source_timestamp(signal_frame, research)
    research_unique_dates = (
        research["data_cutoff_utc"].astype(str).str[:10].nunique()
        if not research.empty and "data_cutoff_utc" in research
        else 0
    )
    return {
        "schema_version": "1.0",
        "name": "Voorspelmonitor",
        "generated_at_utc": latest_source,
        "data_cutoff_utc": latest_cutoff(signal_frame),
        "definition": public_definition(definitions[-1] if definitions else SIGNAL_DEFINITION),
        "status": status,
        "primary_metrics": primary_metrics,
        "evidence_over_time": evidence_over_time(events, outcomes, controls),
        "horizon_profile": horizon_profile(events, outcomes, controls),
        "event_study": event_study(events, signal_frame, research_by_date),
        "stability": stability_slices(events, outcomes, controls),
        "events": event_rows,
        "status_ladder": status_ladder(status["code"]),
        "data_quality": {
            "raw_prediction_rows": raw_prediction_count,
            "first_publications_used": int(len(signal_frame)),
            "duplicate_prediction_dates_ignored": max(
                0, raw_prediction_count - int(len(signal_frame))
            ),
            "research_runs_preserved": int(len(research)),
            "research_unique_dates": int(research_unique_dates),
            "research_duplicate_dates": max(0, int(len(research)) - int(research_unique_dates)),
            "research_duplicate_policy": "Eerste gepubliceerde run per datadag.",
            "definition_rows": len(definitions),
            "event_rows": len(events),
            "outcome_rows": len(outcomes),
            "ledger_validation": "passed",
            "source_sha256": {
                name: file_hash(path) for name, path in source_paths.items() if path.exists()
            },
        },
        "downloads": [
            {
                "label": "Signaaldefinities (JSONL)",
                "path": "./data/signal_definitions.jsonl",
            },
            {
                "label": "Events (JSONL)",
                "path": "./data/signal_events.jsonl",
            },
            {
                "label": "Uitkomsten (JSONL)",
                "path": "./data/signal_outcomes.jsonl",
            },
            {"label": "Monitor (JSON)", "path": "./data/predictive_monitor.json"},
        ],
        "methodology": [
            (
                "De scorepiek wordt pas één officiële observatie later bevestigd; de "
                "regel gebruikt dus geen toekomstinformatie op het moment van het event."
            ),
            (
                "Alleen clusterstarts tellen als event. Een cooldown van tien dagen "
                "voorkomt dat opeenvolgende dagen als onafhankelijke bewijzen worden geteld."
            ),
            (
                "De primaire uitkomst is het SOL-rendement na zeven kalenderdagen ten "
                "opzichte van alle volwassen officiële controledagen met minder dan drie pieken."
            ),
            (
                "Het rendementsanker is de slotkoers op de data-cutoff-dag in de officiële "
                "prediction. Het eerste publicatietijdstip wordt apart in het eventregister "
                "getoond en een event gebruikt altijd de eerste publicatie van die datadag."
            ),
            (
                "SOL-minus-BTC en de richting-hit-rate zijn vooraf vastgelegde "
                "nevenmetingen; 1, 3, 14 en 30 dagen zijn gevoeligheidsprofielen."
            ),
            (
                "Historische backfill blijft retrospectief. Alleen na de lock gepubliceerde "
                "events tellen mee voor de bevestigingsdrempels."
            ),
            (
                "Een methodewijziging krijgt een nieuw versienummer en een nieuwe "
                "definitieregel; events en uitkomsten zijn append-only en gehasht."
            ),
        ],
        "limitations": [
            (
                "De piekregel is na historische inspectie gekozen. De huidige vier volwassen "
                "7-daagse events zijn daarom hypothesevormend, niet bevestigend."
            ),
            (
                "Controledagen overlappen in tijd. Hun gemiddelde is een beschrijvende "
                "benchmark; de onafhankelijke eventtelling bepaalt de bewijsstatus."
            ),
            (
                "Met vier volwassen events zijn betrouwbaarheidsintervallen breed en "
                "regime-uitsplitsingen zeer klein."
            ),
            (
                "Transactiekosten, slippage, liquiditeit en uitvoerbaarheid zijn niet "
                "verwerkt; statistische en economische relevantie worden apart getoond."
            ),
            (
                "De data-cutoff-slotkoers is een reproduceerbaar statistisch anker, geen "
                "gegarandeerde uitvoeringsprijs op het latere publicatietijdstip."
            ),
            (
                "Meerdere verkende specificaties vergroten de kans op een toevallig "
                "patroon. Prospectieve resultaten zijn daarom doorslaggevend."
            ),
        ],
    }


def public_definition(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "definition_id",
        "candidate_name",
        "version",
        "status",
        "locked_at_utc",
        "discovery_period",
        "prospective_policy",
        "input_policy",
        "peak_rule",
        "feature",
        "event_rule",
        "cooldown_days",
        "primary_horizon_days",
        "secondary_horizons_days",
        "control_policy",
        "change_policy",
        "economic_relevance_threshold",
        "discovery_note",
        "payload_sha256",
    ]
    return {key: row.get(key) for key in keys}


def publish_ledger_copies(root: Path, paths: list[Path]) -> None:
    """Expose byte-identical, read-only copies in the static Pages artifact."""
    public_dir = root / "site" / "data"
    public_dir.mkdir(parents=True, exist_ok=True)
    for source in paths:
        target = public_dir / source.name
        content = source.read_bytes()
        if not target.exists() or target.read_bytes() != content:
            target.write_bytes(content)


def control_observations(
    frame: pd.DataFrame, research_by_date: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    prices = {str(row["date"]): row for _, row in frame.iterrows()}
    controls: list[dict[str, Any]] = []
    eligible = frame[frame["feature_ready"] & (frame["peak_count_10d"] < 3)]
    for _, row in eligible.iterrows():
        date = pd.Timestamp(row["date"])
        entry_text = date.date().isoformat()
        entry_btc = clean_number(research_by_date.get(entry_text, {}).get("btc_price"))
        for horizon in HORIZONS:
            maturity = date + pd.Timedelta(days=horizon)
            maturity_text = maturity.date().isoformat()
            exit_row = prices.get(maturity_text)
            if exit_row is None:
                continue
            sol_return = return_value(row["sol_price"], exit_row.get("sol_price"))
            exit_btc = clean_number(research_by_date.get(maturity_text, {}).get("btc_price"))
            btc_return = return_value(entry_btc, exit_btc)
            controls.append(
                {
                    "entry_date": entry_text,
                    "maturity_date": maturity_text,
                    "evaluation_phase": (
                        "prospective"
                        if str(row.get("created_at_utc")) >= LOCKED_AT_UTC
                        else "retrospective"
                    ),
                    "horizon_days": horizon,
                    "sol_return": sol_return,
                    "btc_relative_return": (
                        None
                        if sol_return is None or btc_return is None
                        else sol_return - btc_return
                    ),
                    "direction_positive": None if sol_return is None else sol_return > 0,
                }
            )
    return controls


def build_primary_metrics(
    events: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    controls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    event_outcomes = outcome_rows(outcomes, PRIMARY_HORIZON)
    control_rows = [row for row in controls if row["horizon_days"] == PRIMARY_HORIZON]
    pairs = [
        (
            "sol_uplift_7d",
            "SOL-rendementsuplift (7d)",
            "sol_return",
            "percentage_points",
            "Gemiddeld 7-daags SOL-rendement minus controledagen",
        ),
        (
            "btc_relative_uplift_7d",
            "BTC-relatieve uplift (7d)",
            "btc_relative_return",
            "percentage_points",
            "Gemiddeld SOL-minus-BTC rendement minus controledagen",
        ),
        (
            "directional_uplift_7d",
            "Directionele uplift (7d)",
            "direction_positive",
            "percentage_points",
            "Aandeel positieve events minus positieve controledagen",
        ),
    ]
    result = []
    for metric_id, label, field, unit, benchmark in pairs:
        event_values = numeric_values(event_outcomes, field)
        control_values = numeric_values(control_rows, field)
        estimate = difference_of_means(event_values, control_values)
        ci_low, ci_high = bootstrap_difference_ci(
            event_values, control_values, seed=seed_for(metric_id)
        )
        prospective_values = numeric_values(
            [row for row in event_outcomes if row.get("evaluation_phase") == "prospective"],
            field,
        )
        prospective_control_values = numeric_values(
            [row for row in control_rows if row.get("evaluation_phase") == "prospective"],
            field,
        )
        prospective_estimate = difference_of_means(
            prospective_values, prospective_control_values
        )
        prospective_ci = bootstrap_difference_ci(
            prospective_values,
            prospective_control_values,
            seed=seed_for(f"{metric_id}_prospective"),
        )
        retrospective_values = numeric_values(
            [row for row in event_outcomes if row.get("evaluation_phase") == "retrospective"],
            field,
        )
        early, late = split_early_late(event_outcomes, field, control_values)
        result.append(
            {
                "metric_id": metric_id,
                "label": label,
                "unit": unit,
                "estimate": rounded(estimate, 10),
                "ci95": [rounded(ci_low, 10), rounded(ci_high, 10)],
                "event_mean": rounded(mean_or_none(event_values), 10),
                "control_mean": rounded(mean_or_none(control_values), 10),
                "independent_event_n": len(event_values),
                "control_window_n": len(control_values),
                "prospective_event_n": len(prospective_values),
                "prospective_control_n": len(prospective_control_values),
                "prospective_estimate": rounded(prospective_estimate, 10),
                "prospective_ci95": [
                    rounded(prospective_ci[0], 10),
                    rounded(prospective_ci[1], 10),
                ],
                "retrospective_event_n": len(retrospective_values),
                "benchmark": benchmark,
                "early_split": early,
                "late_split": late,
                "economic_threshold": (
                    0.02 if metric_id == "sol_uplift_7d" else None
                ),
                "economically_relevant": (
                    None
                    if metric_id != "sol_uplift_7d" or estimate is None
                    else estimate >= 0.02
                ),
                "evidence_scope": (
                    "mixed_retrospective_and_prospective"
                    if prospective_values
                    else "retrospective_exploratory"
                ),
            }
        )
    return result


def outcome_rows(outcomes: list[dict[str, Any]], horizon: int) -> list[dict[str, Any]]:
    return sorted(
        [row for row in outcomes if int(row.get("horizon_days") or 0) == horizon],
        key=lambda row: str(row.get("maturity_date")),
    )


def evidence_over_time(
    events: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    controls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    del events
    primary = outcome_rows(outcomes, PRIMARY_HORIZON)
    rows = []
    for index, outcome in enumerate(primary, start=1):
        available_events = primary[:index]
        maturity = str(outcome["maturity_date"])
        available_controls = [
            row
            for row in controls
            if row["horizon_days"] == PRIMARY_HORIZON
            and str(row["maturity_date"]) <= maturity
        ]
        event_values = numeric_values(available_events, "sol_return")
        control_values = numeric_values(available_controls, "sol_return")
        estimate = difference_of_means(event_values, control_values)
        low, high = bootstrap_difference_ci(
            event_values, control_values, seed=17_000 + index
        )
        rows.append(
            {
                "maturity_date": maturity,
                "event_n": len(event_values),
                "control_n": len(control_values),
                "estimate": rounded(estimate, 10),
                "ci95_low": rounded(low, 10),
                "ci95_high": rounded(high, 10),
            }
        )
    return rows


def horizon_profile(
    events: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    controls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    del events
    rows = []
    for horizon in HORIZONS:
        event_values = numeric_values(outcome_rows(outcomes, horizon), "sol_return")
        control_values = numeric_values(
            [row for row in controls if row["horizon_days"] == horizon], "sol_return"
        )
        estimate = difference_of_means(event_values, control_values)
        low, high = bootstrap_difference_ci(
            event_values, control_values, seed=31_000 + horizon
        )
        rows.append(
            {
                "horizon_days": horizon,
                "event_mean": rounded(mean_or_none(event_values), 10),
                "control_mean": rounded(mean_or_none(control_values), 10),
                "uplift": rounded(estimate, 10),
                "ci95_low": rounded(low, 10),
                "ci95_high": rounded(high, 10),
                "event_n": len(event_values),
                "control_n": len(control_values),
                "is_primary": horizon == PRIMARY_HORIZON,
            }
        )
    return rows


def event_study(
    events: list[dict[str, Any]],
    frame: pd.DataFrame,
    research_by_date: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    prices = {str(row["date"]): clean_number(row["sol_price"]) for _, row in frame.iterrows()}
    rows = []
    for offset in range(-5, 15):
        sol_values: list[float] = []
        relative_values: list[float] = []
        for event in events:
            event_date = pd.Timestamp(event["event_date"])
            target_date = (event_date + pd.Timedelta(days=offset)).date().isoformat()
            sol_return = return_value(event.get("sol_entry_price"), prices.get(target_date))
            if sol_return is None:
                continue
            sol_values.append(sol_return)
            btc_target = research_by_date.get(target_date, {}).get("btc_price")
            btc_return = return_value(event.get("btc_entry_price"), btc_target)
            if btc_return is not None:
                relative_values.append(sol_return - btc_return)
        rows.append(
            {
                "offset_days": offset,
                "sol_mean_return": rounded(mean_or_none(sol_values), 10),
                "btc_relative_mean_return": rounded(mean_or_none(relative_values), 10),
                "event_n": len(sol_values),
            }
        )
    return rows


def stability_slices(
    events: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    controls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    primary = outcome_rows(outcomes, PRIMARY_HORIZON)
    event_map = {row["event_id"]: row for row in events}
    controls_values = numeric_values(
        [row for row in controls if row["horizon_days"] == PRIMARY_HORIZON], "sol_return"
    )
    if not primary:
        return []
    split_at = (len(primary) + 1) // 2
    groups: list[tuple[str, str, list[dict[str, Any]]]] = [
        ("time_early", "Vroege helft", primary[:split_at]),
        ("time_late", "Late helft", primary[split_at:]),
    ]
    vol_values = [
        clean_number((event_map.get(row["event_id"], {}).get("context_at_entry") or {}).get(
            "realized_volatility_30d"
        ))
        for row in primary
    ]
    finite_vol = [value for value in vol_values if value is not None]
    if finite_vol:
        median_vol = float(np.median(finite_vol))
        groups.extend(
            [
                (
                    "volatility_low",
                    "Lagere volatiliteit",
                    [
                        row
                        for row in primary
                        if (
                            value := context_number(
                                event_map, row, "realized_volatility_30d"
                            )
                        )
                        is not None
                        and value <= median_vol
                    ],
                ),
                (
                    "volatility_high",
                    "Hogere volatiliteit",
                    [
                        row
                        for row in primary
                        if (
                            value := context_number(
                                event_map, row, "realized_volatility_30d"
                            )
                        )
                        is not None
                        and value > median_vol
                    ],
                ),
            ]
        )
    groups.extend(
        [
            (
                "btc_momentum_nonpositive",
                "BTC-momentum ≤ 0",
                [
                    row
                    for row in primary
                    if (value := context_number(event_map, row, "btc_return_7d"))
                    is not None
                    and value <= 0
                ],
            ),
            (
                "btc_momentum_positive",
                "BTC-momentum > 0",
                [
                    row
                    for row in primary
                    if (value := context_number(event_map, row, "btc_return_7d"))
                    is not None
                    and value > 0
                ],
            ),
        ]
    )
    for version in sorted(
        {str(event_map.get(row["event_id"], {}).get("method_version")) for row in primary}
    ):
        groups.append(
            (
                f"method_{version}",
                f"Methode {version}",
                [
                    row
                    for row in primary
                    if str(event_map.get(row["event_id"], {}).get("method_version"))
                    == version
                ],
            )
        )
    for month in sorted({str(row.get("maturity_date"))[:7] for row in primary}):
        groups.append(
            (
                f"month_{month}",
                month,
                [row for row in primary if str(row.get("maturity_date"))[:7] == month],
            )
        )
    result = []
    for index, (slice_id, label, rows) in enumerate(groups):
        values = numeric_values(rows, "sol_return")
        estimate = difference_of_means(values, controls_values)
        low, high = bootstrap_difference_ci(values, controls_values, seed=51_000 + index)
        result.append(
            {
                "slice_id": slice_id,
                "label": label,
                "event_n": len(values),
                "estimate": rounded(estimate, 10),
                "ci95_low": rounded(low, 10),
                "ci95_high": rounded(high, 10),
                "sufficient_for_interpretation": len(values) >= 5,
            }
        )
    return result


def event_view(
    events: list[dict[str, Any]], outcomes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_key = {
        (row.get("event_id"), int(row.get("horizon_days") or 0)): row for row in outcomes
    }
    result = []
    for event in sorted(events, key=lambda row: str(row.get("event_date")), reverse=True):
        primary = by_key.get((event.get("event_id"), PRIMARY_HORIZON))
        secondary_14 = by_key.get((event.get("event_id"), 14))
        result.append(
            {
                "event_id": event.get("event_id"),
                "event_date": event.get("event_date"),
                "first_published_at_utc": event.get("first_published_at_utc"),
                "definition_version": event.get("definition_version"),
                "evaluation_phase": event.get("evaluation_phase"),
                "feature_value": event.get("feature_value"),
                "sol_entry_price": event.get("sol_entry_price"),
                "btc_entry_price": event.get("btc_entry_price"),
                "primary_maturity_date": (event.get("maturity_dates") or {}).get("7d"),
                "status": "matured" if primary else "pending",
                "sol_return_7d": None if not primary else primary.get("sol_return"),
                "btc_relative_return_7d": (
                    None if not primary else primary.get("btc_relative_return")
                ),
                "sol_return_14d": (
                    None if not secondary_14 else secondary_14.get("sol_return")
                ),
                "event_payload_sha256": event.get("payload_sha256"),
                "outcome_payload_sha256": (
                    None if not primary else primary.get("payload_sha256")
                ),
            }
        )
    return result


def evaluate_status(
    events: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    controls: list[dict[str, Any]],
    primary_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    event_map = {row.get("event_id"): row for row in events}
    prospective = [
        row
        for row in outcome_rows(outcomes, PRIMARY_HORIZON)
        if row.get("evaluation_phase") == "prospective"
    ]
    retrospective = [
        row
        for row in outcome_rows(outcomes, PRIMARY_HORIZON)
        if row.get("evaluation_phase") == "retrospective"
    ]
    exploratory_sol_metric = next(
        (row for row in primary_metrics if row["metric_id"] == "sol_uplift_7d"), {}
    )
    control_rows = [
        row
        for row in controls
        if row["horizon_days"] == PRIMARY_HORIZON
        and row.get("evaluation_phase") == "prospective"
    ]
    prospective_sol = numeric_values(prospective, "sol_return")
    prospective_relative = numeric_values(prospective, "btc_relative_return")
    control_sol = numeric_values(control_rows, "sol_return")
    control_relative = numeric_values(control_rows, "btc_relative_return")
    sol_ci = bootstrap_difference_ci(
        prospective_sol, control_sol, seed=seed_for("prospective_sol_status")
    )
    btc_ci = bootstrap_difference_ci(
        prospective_relative,
        control_relative,
        seed=seed_for("prospective_btc_status"),
    )
    prospective_n = len(prospective)
    split_at = (prospective_n + 1) // 2
    early = difference_of_means(
        numeric_values(prospective[:split_at], "sol_return"), control_sol
    )
    late = difference_of_means(
        numeric_values(prospective[split_at:], "sol_return"), control_sol
    )
    direction_stable = (
        early is not None and late is not None and (early >= 0) == (late >= 0)
    )
    prospective_uplift = difference_of_means(prospective_sol, control_sol)
    regimes = len(
        {
            event_map.get(row.get("event_id"), {}).get("regime")
            for row in prospective
            if event_map.get(row.get("event_id"), {}).get("regime") is not None
        }
    )
    code = "prospective_in_progress"
    label = "Prospectieve toets in opbouw"
    explanation = (
        "De regel staat vast, maar er zijn nog minder dan twintig volwassen "
        "prospectieve events. Historische events blijven verkennend."
    )
    if prospective_n >= 20:
        if sol_ci[1] is not None and sol_ci[1] < 0:
            code = "not_confirmed"
            label = "Niet bevestigd"
            explanation = "De vooraf vastgelegde primaire toets wijst niet op positieve uplift."
        elif not direction_stable:
            code = "unstable"
            label = "Instabiel"
            explanation = "Het effect wisselt van richting tussen de vooraf gemelde perioden."
        elif sol_ci[0] is not None and sol_ci[0] > 0:
            code = "provisionally_confirmed"
            label = "Voorlopig bevestigd"
            explanation = "De primaire prospectieve drempel is gehaald; robuustheid ontbreekt nog."
            if (
                prospective_n >= 40
                and btc_ci[0] is not None
                and btc_ci[0] > 0
                and regimes >= 2
            ):
                code = "robust"
                label = "Robuust"
                explanation = (
                    "De prospectieve, BTC-relatieve en multi-regime drempels zijn gehaald."
                )
    return {
        "code": code,
        "label": label,
        "explanation": explanation,
        "locked_at_utc": LOCKED_AT_UTC,
        "prospective_mature_event_n": prospective_n,
        "retrospective_mature_event_n": len(retrospective),
        "minimum_for_first_confirmation": 20,
        "minimum_for_robust": 40,
        "statistical_confirmation": code in {"provisionally_confirmed", "robust"},
        "economic_relevance": (
            None if prospective_uplift is None else prospective_uplift >= 0.02
        ),
        "historical_economic_relevance": exploratory_sol_metric.get(
            "economically_relevant"
        ),
        "early_late_direction_stable": direction_stable,
        "multi_regime_prospective": regimes >= 2,
    }


def status_ladder(active_code: str) -> list[dict[str, Any]]:
    return [
        {
            "code": "exploratory",
            "label": "Verkennend",
            "criterion": "Nog geen vastgelegde definitie; alleen hypothesevorming.",
            "active": active_code == "exploratory",
        },
        {
            "code": "prospective_in_progress",
            "label": "Prospectieve toets in opbouw",
            "criterion": "Definitie vastgelegd; minder dan 20 volwassen prospectieve events.",
            "active": active_code == "prospective_in_progress",
        },
        {
            "code": "provisionally_confirmed",
            "label": "Voorlopig bevestigd",
            "criterion": (
                "Minimaal 20 prospectieve events, 95%-interval boven nul en "
                "stabiele richting."
            ),
            "active": active_code == "provisionally_confirmed",
        },
        {
            "code": "robust",
            "label": "Robuust",
            "criterion": "Minimaal 40 events plus BTC-relatieve en multi-regime bevestiging.",
            "active": active_code == "robust",
        },
        {
            "code": "unstable",
            "label": "Instabiel",
            "criterion": "Voldoende events, maar richting of regime-uitkomsten zijn niet stabiel.",
            "active": active_code == "unstable",
        },
        {
            "code": "not_confirmed",
            "label": "Niet bevestigd",
            "criterion": "De vooraf vastgelegde primaire toets is negatief.",
            "active": active_code == "not_confirmed",
        },
    ]


def split_early_late(
    rows: list[dict[str, Any]], field: str, controls: list[float]
) -> tuple[dict[str, Any], dict[str, Any]]:
    split_at = (len(rows) + 1) // 2
    parts = [rows[:split_at], rows[split_at:]]
    result = []
    for part in parts:
        values = numeric_values(part, field)
        result.append(
            {
                "estimate": rounded(difference_of_means(values, controls), 10),
                "event_n": len(values),
            }
        )
    return result[0], result[1]


def numeric_values(rows: Iterable[dict[str, Any]], field: str) -> list[float]:
    values = []
    for row in rows:
        value = row.get(field)
        if isinstance(value, bool):
            values.append(float(value))
        else:
            number = clean_number(value)
            if number is not None:
                values.append(number)
    return values


def difference_of_means(left: list[float], right: list[float]) -> float | None:
    if not left or not right:
        return None
    return float(np.mean(left) - np.mean(right))


def bootstrap_difference_ci(
    left: list[float], right: list[float], seed: int, iterations: int = 10_000
) -> tuple[float | None, float | None]:
    if not left or not right:
        return None, None
    rng = np.random.default_rng(seed)
    a = np.asarray(left, dtype=float)
    b = np.asarray(right, dtype=float)
    boot_a = rng.choice(a, size=(iterations, len(a)), replace=True).mean(axis=1)
    # Seven-row circular blocks preserve part of the overlap in daily control windows.
    block = min(7, len(b))
    starts = rng.integers(0, len(b), size=(iterations, int(np.ceil(len(b) / block))))
    offsets = np.arange(block)
    indices = (starts[:, :, None] + offsets[None, None, :]) % len(b)
    boot_b = b[indices.reshape(iterations, -1)[:, : len(b)]].mean(axis=1)
    samples = boot_a - boot_b
    low, high = np.quantile(samples, [0.025, 0.975])
    return float(low), float(high)


def context_number(
    event_map: dict[str, dict[str, Any]], row: dict[str, Any], field: str
) -> float | None:
    event = event_map.get(str(row.get("event_id")), {})
    return clean_number((event.get("context_at_entry") or {}).get(field))


def return_value(entry: Any, exit_value: Any) -> float | None:
    start = clean_number(entry)
    end = clean_number(exit_value)
    if start is None or end is None or start == 0:
        return None
    return end / start - 1


def mean_or_none(values: list[float]) -> float | None:
    return None if not values else float(np.mean(values))


def clean_number(value: Any) -> float | None:
    if value is None or isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def clean_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


def rounded(value: Any, digits: int) -> float | None:
    number = clean_number(value)
    return None if number is None else round(number, digits)


def latest_cutoff(frame: pd.DataFrame) -> str | None:
    if frame.empty:
        return None
    return f"{frame['date'].max()}T23:59:59Z"


def latest_source_timestamp(frame: pd.DataFrame, research: pd.DataFrame) -> str | None:
    values: list[str] = []
    if not frame.empty:
        values.extend(str(value) for value in frame["created_at_utc"].dropna())
    if not research.empty and "run_at_utc" in research:
        values.extend(str(value) for value in research["run_at_utc"].dropna())
    return max(values) if values else None


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_for(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:8], 16)
