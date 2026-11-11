"""Read-only attribution of the original blue score, never inferred from later prices."""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from sol_reality_check.ledger import read_jsonl

COMPONENTS = [
    (
        "out_of_sample_quality",
        "Historische voorspelkwaliteit",
        0.30,
        "Kansfout van de oorspronkelijke 7-daagse analogietest tegenover zijn eigen benchmark. "
        "Score = 55 + 400 × Brier skill, begrensd op 0–100; "
        "dit is de oorspronkelijke analogietest.",
    ),
    (
        "data_quality",
        "Datakwaliteit",
        0.25,
        "Begint op 100; aftrek bij onder meer prijsreparaties, herstelbronnen en bronafwijkingen.",
    ),
    (
        "stability",
        "Stabiliteit",
        0.20,
        "De oorspronkelijke formule gebruikt vaste invoer 70. "
        "Geen dagelijks gemeten marktvariabele.",
    ),
    (
        "sample_adequacy",
        "Aantal vergelijkingen",
        0.15,
        "Aantal bruikbare historische analogieën ÷ 40 × 100, maximaal 100.",
    ),
    (
        "analog_similarity",
        "Gelijkenis",
        0.10,
        "Mediaan van de gelijkenisscores van geselecteerde historische dagen; maximaal 100.",
    ),
]

FEATURES = [
    (
        "sol_return_7d",
        "SOL · 7 dagen",
        "Koers & marktpositie",
        "%",
        "SOL-slot / slot 7 dagen eerder − 1.",
    ),
    (
        "sol_return_30d",
        "SOL · 30 dagen",
        "Koers & marktpositie",
        "%",
        "SOL-slot / slot 30 dagen eerder − 1.",
    ),
    (
        "relative_strength_btc_7d",
        "SOL minus BTC · 7 dagen",
        "Koers & marktpositie",
        "pp",
        "SOL-rendement minus BTC-rendement over 7 dagen.",
    ),
    (
        "relative_strength_btc_30d",
        "SOL minus BTC · 30 dagen",
        "Koers & marktpositie",
        "pp",
        "SOL-rendement minus BTC-rendement over 30 dagen.",
    ),
    (
        "price_vs_sma50",
        "Afstand tot 50-daagse trend",
        "Koers & marktpositie",
        "%",
        "SOL-slot / gemiddelde van 50 dagsloten − 1.",
    ),
    (
        "realized_volatility_30d",
        "Volatiliteit · 30 dagen",
        "Koers & marktpositie",
        "%",
        "Standaardafwijking van 30 dagelijkse log-rendementen × √365. Geen richtingssignaal.",
    ),
    (
        "drawdown_90d",
        "Afstand tot 90-daagse top",
        "Koers & marktpositie",
        "%",
        "SOL-slot / hoogste dagslot over 90 dagen − 1.",
    ),
    (
        "dex_volume_ratio_7d_30d",
        "DEX-handelsactiviteit",
        "Netwerkactiviteit",
        "×",
        "7-daags volumetotaal / gemiddeld dagvolume over 30 dagen. Bij constant volume circa 7×.",
    ),
    (
        "fees_ratio_7d_30d",
        "Netwerkfees",
        "Netwerkactiviteit",
        "×",
        "7-daags feetotaal / gemiddelde dagelijkse fees over 30 dagen. "
        "Bij constante fees circa 7×.",
    ),
    (
        "tvl_change_30d",
        "TVL · 30 dagen",
        "Kapitaal & liquiditeit",
        "%",
        "Verandering in vastgelegde DeFi-dollarwaarde over 30 dagen; inclusief prijseffecten.",
    ),
    (
        "stablecoin_change_30d",
        "Stablecoins · 30 dagen",
        "Kapitaal & liquiditeit",
        "%",
        "Verandering in stablecoin-dollarvoorraad op Solana over 30 dagen; "
        "geen gemeten SOL-koopstroom.",
    ),
]


def cap_ceiling(reasons: list[str]) -> float | None:
    limits = {
        "Minder dan 20 effectieve analogieën": 45,
        "Voorspelkwaliteit ≤ 0": 55,
        "Minder dan 100 out-of-sample voorspellingen": 55,
        "Twee of meer ontbrekende hoofdbronnen": 0,
        "Kritieke datavalidatiefout": 0,
    }
    values = [v for k, v in limits.items() if k in reasons]
    return float(min(values)) if values else None


def explain_blue(
    root: Path, history: list[dict[str, Any]], predictions: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    archives = {}
    for entry in read_jsonl(root / "data/research/runs.jsonl"):
        content = gzip.decompress((root / entry["file"]).read_bytes())
        if hashlib.sha256(content).hexdigest() != entry["input_sha256"]:
            raise ValueError("Blue score input archive hash mismatch")
        archived = json.loads(content)
        archives[entry["run_at_utc"]] = (archived, entry)
    research = pd.read_parquet(root / "data/curated/signaalonderzoek.parquet")
    weights = yaml.safe_load((root / "config/indicators.yml").read_text())["analog_features"]
    total_weight = sum(weights.values())
    breakdown, market = [], []
    for point in history:
        prediction = predictions[point["source_sha256"]]
        archive, entry = archives.get(point["published_at"], ({}, {}))
        archived = archive.get("dashboard", {})
        # Exact timestamp AND output identity: never attach a later rerun to an earlier publication.
        matches = (
            archived.get("data_cutoff_utc", "")[:10] == point["date"]
            and archived.get("scores", {}).get("evidence_quality") == point["quality_score"]
            and archived.get("current", {}).get("sol_price", point["sol_close"])
            == point["sol_close"]
        )
        components = archived.get("scores", {}).get("evidence_components", {}) if matches else {}
        analog = prediction.get("horizons", {}).get("7d", {})
        reasons = prediction.get("quality_caps", [])
        row = {
            "date": point["date"],
            "published_at": point["published_at"],
            "published_time": point["published_time"],
            "score": point["quality_score"],
            "source_sha256": point["source_sha256"],
            "prediction_id": point["prediction_id"],
            "input_file": entry.get("file") if matches else None,
            "input_sha256": entry.get("input_sha256") if matches else None,
            "ceiling": cap_ceiling(reasons),
            "reasons": reasons,
            "analog_count": analog.get("count"),
            "median_similarity": analog.get("median_similarity"),
            "complete": all(components.get(c[0]) is not None for c in COMPONENTS),
        }
        for key, _, weight, _ in COMPONENTS:
            # Stored horizon facts give two partial components. Weighting them with
            # the documented v1 formula is explicitly a reconstruction, never an archive.
            value = components.get(key)
            provenance = "Oorspronkelijk opgeslagen" if value is not None else "Niet opgeslagen"
            if value is None and prediction.get("method_version") == "1.0.0":
                if key == "sample_adequacy" and analog.get("count") is not None:
                    value = min(100, analog["count"] / 40 * 100)
                elif key == "analog_similarity" and analog.get("median_similarity") is not None:
                    value = min(100, analog["median_similarity"])
                if value is not None:
                    provenance = "Gereconstrueerd uit opgeslagen analogieën · formule v1"
            row[key] = value
            row[f"{key}_points"] = value * weight if value is not None else None
            row[f"{key}_provenance"] = provenance
        row["raw_score"] = (
            sum(row[f"{c[0]}_points"] for c in COMPONENTS) if row["complete"] else None
        )
        if row["complete"]:
            expected = (
                min(row["raw_score"], row["ceiling"])
                if row["ceiling"] is not None
                else row["raw_score"]
            )
            if abs(expected - row["score"]) > 0.03:
                raise ValueError("Archived blue score does not reconcile with its components")
        breakdown.append(row)
        eligible = research[
            (research.data_cutoff_utc.str[:10] == point["date"])
            & (research.run_at_utc <= point["published_at"])
        ].sort_values("run_at_utc")
        original = eligible.iloc[0] if len(eligible) else None
        exact_inputs = False
        if matches and archive.get("history"):
            stored_history = archive["history"]
            if isinstance(stored_history, list):
                full_history = pd.DataFrame(stored_history)
            else:
                parquet_bytes = base64.b64decode(stored_history["bytes_base64"])
                if hashlib.sha256(parquet_bytes).hexdigest() != stored_history["sha256"]:
                    raise ValueError("Archived feature history hash mismatch")
                full_history = pd.read_parquet(io.BytesIO(parquet_bytes))
            selected_input = full_history[full_history.date.astype(str) == point["date"]]
            if len(selected_input) != 1:
                raise ValueError("Archived model input day is not unique")
            original = selected_input.iloc[0].copy()
            original["run_at_utc"] = point["published_at"]
            exact_inputs = True
        for key, label, group, unit, definition in FEATURES:
            value = original.get(key) if original is not None else None
            market.append(
                {
                    "date": point["date"],
                    "published_at": point["published_at"],
                    "feature": key,
                    "label": label,
                    "group": group,
                    "unit": unit,
                    "value": float(value) if value is not None and pd.notna(value) else None,
                    "weight": weights[key],
                    "normalized_weight": weights[key] / total_weight,
                    "definition": definition,
                    "source_run_at": original.run_at_utc if original is not None else None,
                    "provenance": (
                        "Exacte modelinvoer uit geverifieerd runarchief"
                        if exact_inputs
                        else "Opgeslagen beschikbare bronmeting · kan afgerond zijn"
                    )
                    if original is not None
                    else "Niet beschikbaar bij eerste publicatie",
                }
            )
    definitions = [
        dict(key=k, label=label, weight=w, definition=d) for k, label, w, d in COMPONENTS
    ]
    return breakdown, market, definitions
