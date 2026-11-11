"""Read-only, source-backed presentation snapshot for the public research dashboard.

No prices, forecasts, definitions or source ledgers are changed by this exporter.
The price axis uses the close's event time; KPI and forecast axes use the time at
which their information became available. Hypothetical historical marks remain
explicitly reconstructed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sol_reality_check.blue_explainer import explain_blue
from sol_reality_check.config import ROOT
from sol_reality_check.ledger import read_jsonl
from sol_reality_check.research_monitor import build_inputs, load_protocol, prediction_sources
from sol_reality_check.utils import payload_hash, write_json

APP_ID = "dashboard:5955feb0-e9b2-4727-8d30-7b0abd38ffba"
REPO = "https://github.com/jwblank/solana-dashboard"


def load(root: Path, filename: str) -> dict[str, Any]:
    return json.loads((root / "site/data" / filename).read_text(encoding="utf-8"))


def native(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): native(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [native(v) for v in value]
    if isinstance(value, np.generic):
        return native(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def epoch(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1000)


def source(
    label: str,
    files: list[str],
    definitions: list[dict[str, str]],
    caveats: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "files": files,
        "links": [{"label": "Broncode en registraties", "url": REPO}],
        "metricDefinitions": definitions,
        "caveats": caveats or [],
        "evidenceFlow": [
            {
                "kind": "method",
                "title": "Reproduceerbare presentatie",
                "detail": "src/sol_reality_check/lab_snapshot.py leest de bestaande "
                "productiedata. Primaire bronbestanden worden niet geschreven.",
            }
        ],
    }


def quote_method(row: dict[str, Any]) -> str:
    statuses = row.get("source_status", {})
    ccxt = statuses.get("ccxt_price_consensus", {})
    sol = ccxt.get("context", {}).get("sol", {})
    if sol.get("fallback_used"):
        return "Coinbase herstelbron"
    if ccxt.get("available"):
        return "Multi-exchange consensus"
    if statuses.get("coinbase", {}).get("available"):
        return "Coinbase"
    return "Zie oorspronkelijke bronregistratie"


def build_lab_snapshot(root: Path = ROOT) -> dict[str, Any]:
    dashboard = load(root, "dashboard.json")
    if dashboard.get("mode") != "production":
        raise ValueError("The public lab snapshot requires production data; demo cannot replace it")
    monitor = load(root, "research_monitor.json")
    legacy = load(root, "predictive_monitor.json")
    protocol = load_protocol(root)
    # All persisted publications are known at export; individual training/forecast
    # availability was already enforced and frozen by the research monitor.
    available_at = max([dashboard["generated_at_utc"], monitor["generated_at_utc"]])
    frame, prices = build_inputs(root, protocol, available_at)
    predictions = {row["payload_sha256"]: row for row in prediction_sources(root)}
    history = []
    for day, row in frame[frame.prediction_id.notna()].iterrows():
        prediction = predictions[row.prediction_sha256]
        history.append(
            {
                "date": day,
                "close_at": f"{day}T23:59:59Z",
                "close_time": epoch(f"{day}T23:59:59Z"),
                "published_at": row.published_at_utc,
                "published_time": epoch(row.published_at_utc),
                "sol_close": row.sol,
                "btc_close": prices.get(day, {}).get("btc"),
                "blue_duration": row.blue_occupancy_14 * 100,
                "blue_blocks_change": row.blue_blocks_delta7,
                "network_score": row.network,
                "quality_score": row.quality,
                "strength_score": row.score,
                "price_method": quote_method(prediction),
                "prediction_id": row.prediction_id,
                "source_sha256": row.prediction_sha256,
                "components_at": row.components_at_utc if pd.notna(row.components_at_utc) else None,
            }
        )
    fields = {
        "blue-duration-v1": (
            "blue_duration",
            "%",
            None,
            "Modeldiagnostiek",
            "Het aandeel hoge onderbouwingsscores kan informatie toevoegen aan de koersbasis.",
        ),
        "blue-blocks-falling-v1": (
            "blue_blocks_change",
            "blokken",
            0,
            "Modeldiagnostiek",
            "Minder nieuwe hoge blokken kan voorafgaan aan zwakke koersweken.",
        ),
        "network-weakness-v1": (
            "network_score",
            "/100",
            50,
            "Netwerkgebruik",
            "Netwerkzwakte kan informatie bevatten over volgende SOL-rendementen.",
        ),
    }
    candidates = []
    for candidate in monitor["candidates"]:
        field, unit, threshold, family, hypothesis = fields[candidate["candidate_id"]]
        current = next((row[field] for row in reversed(history) if pd.notna(row[field])), None)
        candidates.append(
            {
                "candidate_id": candidate["candidate_id"],
                "name": candidate["name"],
                "field": field,
                "unit": unit,
                "threshold": threshold,
                "family": family,
                "hypothesis": hypothesis,
                "definition": candidate["definition"],
                "current_value": current,
            }
        )
    forecasts = []
    original_forecasts = {
        r["forecast_id"]: r for r in read_jsonl(root / "data/research/forecasts.jsonl")
    }
    for row in monitor["records"]:
        if row["horizon_days"] != 7:
            continue
        original = original_forecasts[row["forecast_id"]]
        if original.get("payload_sha256") != payload_hash(original):
            raise ValueError("Invalid original forecast hash")
        # True forward marks use registration time. Historical marks explicitly
        # use their source time and must never be described as then registered.
        mark_time = (
            row["recorded_at_utc"] if row["phase"] == "prospective" else row["published_at_utc"]
        )
        forecasts.append(
            {
                **row,
                "mark_at": mark_time,
                "mark_time": epoch(mark_time),
                "entry_time": epoch(f"{row['entry_date']}T23:59:59Z"),
                "exit_time": epoch(f"{row['exit_date']}T23:59:59Z"),
                "correct": (row["actual_direction"] == row["predicted_direction"])
                if row.get("actual_direction") and row.get("predicted_direction")
                else None,
                "source_prediction_id": original["source_prediction_id"],
                "source_sha256": original["source_prediction_sha256"],
                "forecast_sha256": original["payload_sha256"],
            }
        )
    evaluations = [
        dict(evaluation, candidate_id=c["candidate_id"], name=c["name"])
        for c in monitor["candidates"]
        for evaluation in c["evaluations"]
    ]
    forward = [r for r in forecasts if r["phase"] == "prospective"]
    mature = [r for r in forward if r.get("sol_return") is not None]
    meta = {
        "data_cutoff": dashboard["data_cutoff_utc"][:10],
        "generated_at": dashboard["generated_at_utc"],
        "research_generated_at": monitor["generated_at_utc"],
        "first_date": history[0]["date"] if history else None,
        "last_date": history[-1]["date"] if history else None,
        "history_days": len(history),
        "research_runs": len(pd.read_parquet(root / "data/curated/signaalonderzoek.parquet")),
        "forward_days": len({r["date"] for r in forward}),
        "mature_forward_days": len({r["date"] for r in mature}),
        "first_maturity": min(
            (r["outcome_after_utc"] for r in forward if r.get("sol_return") is None), default=None
        ),
        "last_close": history[-1]["sol_close"] if history else None,
        "live_check": dashboard["current"].get("live_sol_price"),
        "price_warning": bool(dashboard["current"]["risk"].get("warnings")),
        "price_warnings": dashboard["current"]["risk"].get("warnings", []),
        "price_difference_pct": dashboard["current"]["risk"].get("price_source_difference_pct"),
        "protocol": protocol,
        "baseline_archive": monitor["baseline_archive"],
        "downloads": monitor["downloads"],
        "source_policy": monitor["source_policy"],
        "shadow_quality": monitor.get("shadow_quality", [])[-1:],
        "weekday_diagnostics": monitor.get("weekday_diagnostics", []),
        "legacy_status": legacy["status"],
        "legacy_metrics": legacy["primary_metrics"],
        "legacy_events": legacy["events"],
        "llm": load(root, "interpretation.json"),
        "research_note": (
            load(root, "research_note.json")
            if (root / "site/data/research_note.json").exists()
            else None
        ),
    }
    quality_sources, price_checks = [], []
    for row in dashboard.get("data_audit", {}).get("sources", []):
        quality_sources.append({k: v for k, v in row.items() if k != "price_breakdown"})
        for check in row.get("price_breakdown", []):
            for exchange in check.get("exchange_prices", []):
                price_checks.append(
                    {
                        "asset": check.get("asset"),
                        "date": check.get("date"),
                        "used_close": check.get("used_close"),
                        "method": check.get("method"),
                        **exchange,
                    }
                )
    caveats = [
        "Prijsniveaus en KPI's kunnen samen bewegen zonder extra voorspelkracht.",
        "Historische reconstructies zijn verkennend; nieuwe toetsuitkomsten staan apart.",
        "Dagelijkse weekuitkomsten overlappen. Niet-overlap is geen garantie op onafhankelijkheid.",
        "Koersen op de grafiek zijn oorspronkelijke dagsloten, geen intraday uitvoeringsprijzen.",
    ]
    q = {
        "history": {
            "rows": native(history),
            "source": source(
                "Oorspronkelijke koers- en KPI-publicaties",
                [
                    "data/ledger/predictions.jsonl",
                    "data/research/parallel_predictions.jsonl",
                    "data/curated/signaalonderzoek.parquet",
                ],
                [
                    {
                        "label": "SOL-dagslot",
                        "definition": "Het oorspronkelijke opgeslagen SOL-slot "
                        "op het einde van de UTC-datadag. Bronmethode en beschikbaarheid "
                        "staan per punt vast.",
                    },
                    {
                        "label": "KPI-tijdstip",
                        "definition": "Een KPI wordt getekend op zijn eerste "
                        "publicatietijdstip, niet teruggeschoven naar een eerder koersmoment.",
                    },
                ],
                caveats,
            ),
        },
        "forecasts": {
            "rows": forecasts,
            "source": source(
                "Onveranderlijke voorspellingen en uitkomsten",
                ["data/research/forecasts.jsonl", "data/research/outcomes.jsonl"],
                [
                    {
                        "label": "Vooraf vastgelegd",
                        "definition": "Nieuwe voorspellingen staan op "
                        "het registratiemoment. Reconstructies op hun bronmoment, "
                        "expliciet als verkenning.",
                    },
                    {"label": "Meetvenster", "definition": protocol["entry_policy"]},
                ],
                caveats,
            ),
        },
        "candidates": {
            "rows": candidates,
            "source": source(
                "Vaste onderzoekskandidaten",
                ["config/research_protocol.json"],
                [{"label": c["name"], "definition": c["definition"]} for c in candidates],
            ),
        },
        "evaluations": {
            "rows": evaluations,
            "source": source(
                "Gepaarde modelvergelijking",
                ["site/data/research_monitor.json"],
                [
                    {
                        "label": "Extra voorspelkracht",
                        "definition": "Brier-fout van de koersbasis "
                        "minus de fout van dezelfde basis met één kandidaat, "
                        "op dezelfde meetdagen. "
                        "Positief is gunstiger. Een interval met nul laat de meerwaarde onzeker.",
                    },
                    {"label": "95%-interval", "definition": protocol["uncertainty_policy"]},
                ],
                monitor["limitations"],
            ),
        },
        "source_quality": {
            "rows": quality_sources,
            "source": source(
                "Bestaande broncontroles",
                ["site/data/dashboard.json", "site/data/source_status.json"],
                [
                    {
                        "label": "Herstelbron",
                        "definition": "Een opgevraagde bron is niet automatisch "
                        "een gebruikte bron. Een terugval op Coinbase blijft expliciet zichtbaar.",
                    }
                ],
            ),
        },
        "price_checks": {
            "rows": price_checks,
            "source": source(
                "Recente exchange-controle",
                ["site/data/source_status.json"],
                [
                    {
                        "label": "Gebruikt",
                        "definition": "Alleen bronregels met used=true droegen "
                        "bij aan de betreffende opgeslagen controleprijs. Controle-datum en "
                        "dagslotdatum kunnen verschillen; USD en USDT worden "
                        "niet stilzwijgend gelijkgesteld.",
                    }
                ],
            ),
        },
        "meta": {
            "rows": [meta],
            "source": source(
                "Onderzoeksstand en protocol",
                ["site/data/build_info.json", "config/research_protocol.json"],
                [
                    {
                        "label": "Meetdag",
                        "definition": "Eén datadag, niet één losse run of drie "
                        "kandidaten. De nieuwe toets deelt de meetdagen, "
                        "maar beoordeelt elke kandidaat apart.",
                    }
                ],
            ),
        },
        "event_paths": {
            "rows": event_paths(forecasts, prices),
            "source": source(
                "Beschrijvend koerspad na de dalingsregels",
                ["data/research/forecasts.jsonl", "data/ledger/predictions.jsonl"],
                [
                    {
                        "label": "Gemiddeld pad",
                        "definition": "Alle volledige 7-daagse meetvensters "
                        "met of zonder actieve dalingsregel. Dag 0 is het instapslot. "
                        "95%-banden komen uit een moving-block bootstrap van dagvensters; "
                        "marktregimes zijn niet gematcht. "
                        "Geen causale of uitvoerbare handelsclaim.",
                    }
                ],
                caveats,
            ),
        },
    }
    blue, market, components = explain_blue(root, history, predictions)
    for key, rows, label, files in [
        (
            "blue_breakdown",
            blue,
            "Oorspronkelijke opbouw en begrenzingen",
            ["data/research/runs.jsonl", "data/ledger/predictions.jsonl"],
        ),
        (
            "market_features",
            market,
            "Elf oorspronkelijke marktvariabelen",
            ["data/curated/signaalonderzoek.parquet", "config/indicators.yml"],
        ),
        (
            "blue_components",
            components,
            "Vijf gewogen scoreonderdelen",
            ["src/sol_reality_check/analytics.py"],
        ),
    ]:
        q[key] = {
            "rows": rows,
            "source": source(
                label,
                files,
                [],
                [
                    "Dezelfde eerste publicatie als de hoofdlijn; "
                    "latere runs worden niet teruggeplaatst.",
                    "Ontbrekende details blijven leeg. "
                    "Herleide deelbijdragen zijn expliciet gereconstrueerd.",
                    "Alleen dagen met volledige opgeslagen opbouw krijgen een gestapeld vlak.",
                ],
            ),
        }
    return native(
        {
            "id": APP_ID,
            "title": "SOL Reality Check",
            "surface": "dashboard",
            "buildStatus": "complete",
            "status": "actual",
            "generatedAt": dashboard["generated_at_utc"],
            "filters": [],
            "queries": q,
        }
    )


def event_paths(
    forecasts: list[dict[str, Any]], prices: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for candidate in ["blue-blocks-falling-v1", "network-weakness-v1"]:
        for phase in ["prospective", "reconstructed"]:
            selected = [
                r
                for r in forecasts
                if r["candidate_id"] == candidate
                and r["phase"] == phase
                and r.get("sol_return") is not None
                and r.get("active") is not None
            ]
            paths, flags = [], []
            for row in selected:
                days = [
                    (pd.Timestamp(row["entry_date"]) + pd.Timedelta(days=i)).date().isoformat()
                    for i in range(8)
                ]
                values = [prices.get(day, {}).get("sol") for day in days]
                if any(value is None or value <= 0 for value in values):
                    continue
                paths.append(np.array(values, dtype=float) / values[0] - 1)
                flags.append(bool(row["active"]))
            if not paths:
                continue
            matrix = np.stack(paths)
            flags_array = np.array(flags)
            # Resample adjacent daily windows together, retaining serial dependence.
            rng = np.random.default_rng(20261111)
            n = len(matrix)
            starts = rng.integers(0, n, (1000, int(np.ceil(n / 7))))
            indices = ((starts[:, :, None] + np.arange(7)) % n).reshape(1000, -1)[:, :n]
            for active, label in [(True, "Regel actief"), (False, "Overige meetdagen")]:
                count = int((flags_array == active).sum())
                if not count:
                    continue
                mean = matrix[flags_array == active].mean(axis=0)
                samples = []
                if count >= 5:
                    for ix in indices:
                        chosen = ix[flags_array[ix] == active]
                        if len(chosen) >= 3:
                            samples.append(matrix[chosen].mean(axis=0))
                ci = np.quantile(samples, [0.025, 0.975], axis=0) if len(samples) > 100 else None
                for day in range(8):
                    result.append(
                        {
                            "candidate_id": candidate,
                            "phase": phase,
                            "day": day,
                            "group": label,
                            "mean_pct": float(mean[day] * 100),
                            "lo_pct": float(ci[0, day] * 100) if ci is not None else None,
                            "hi_pct": float(ci[1, day] * 100) if ci is not None else None,
                            "n": count,
                        }
                    )
    return result


def export_lab_snapshot(root: Path = ROOT) -> dict[str, Any]:
    snapshot = build_lab_snapshot(root)
    write_json(root / "site/data/lab_snapshot.json", snapshot)
    write_json(root / "web/src/data.json", snapshot)
    return snapshot
