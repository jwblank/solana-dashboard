"""Calendar-balanced alternative, recorded beside the original quality score."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from sol_reality_check.analytics import analog_summary, brier_score, evidence_quality, find_analogs
from sol_reality_check.predictive_monitor import append_immutable

SHADOW_DEFINITION: dict[str, Any] = {
    "definition_id": "calendar-balanced-quality-v1",
    "version": "1.0.0",
    "weeks": 26,
    "horizon_days": 7,
    "description": (
        "Evalueer alle 182 dagelijkse testmomenten in de laatste 26 volledige "
        "maandag-zondagweken waarvan de 7-daagse uitkomst al bekend is. "
        "Elke weekdag weegt daardoor even zwaar."
    ),
    "benchmark_policy": (
        "Uitbreidend stijgingsaandeel, uitsluitend eerdere testuitkomsten; eerste kans 0,5."
    ),
    "role": (
        "Alternatieve onderbouwing; geen vervanging van de oorspronkelijke score en geen koerskans."
    ),
    "limitations": (
        "De dagelijkse 7-daagse testuitkomsten overlappen. Kalenderbalans lost "
        "steekproeffase op, maar bewijst geen voorspelkracht of dagelijkse onafhankelijkheid."
    ),
}


def balanced_backtest(frame: pd.DataFrame, weights: dict[str, float]) -> dict[str, Any]:
    frame = frame.reset_index(drop=True)
    horizon = SHADOW_DEFINITION["horizon_days"]
    eligible = frame.iloc[365 : len(frame) - horizon]
    if eligible.empty:
        return {"available": False, "reason": "Te weinig historische invoer."}
    last_day = pd.Timestamp(eligible.iloc[-1]["date"])
    last_sunday = last_day - pd.Timedelta(days=(last_day.dayofweek + 1) % 7)
    first_monday = last_sunday - pd.Timedelta(days=181)
    selected = eligible[pd.to_datetime(eligible.date).between(first_monday, last_sunday)]
    weekdays = pd.to_datetime(selected.date).dt.dayofweek.value_counts()
    expected_dates = pd.date_range(first_monday, last_sunday).strftime("%Y-%m-%d").tolist()
    if selected.date.astype(str).tolist() != expected_dates or any(
        weekdays.get(day, 0) != 26 for day in range(7)
    ):
        return {"available": False, "reason": "Nog geen 26 volledige weken met alle weekdagen."}
    rows = []
    for idx, row in selected.iterrows():
        analogs = find_analogs(frame, int(idx), weights, horizon)
        summary = analog_summary(analogs, horizon)
        if summary["count"] < 10:
            return {"available": False, "reason": "Onvoldoende analogieën op een testdag."}
        actual = frame.loc[int(idx) + horizon, "sol_close"] / row.sol_close - 1
        rows.append(
            {
                "date": str(row.date),
                "probability": summary["positive_frequency"],
                "actual_return": float(actual),
                "actual_positive": bool(actual > 0),
            }
        )
    tested = pd.DataFrame(rows)
    actual = tested.actual_positive.astype(float)
    benchmark = actual.expanding().mean().shift(1).fillna(0.5)
    score = brier_score(tested.probability, actual)
    reference = brier_score(benchmark, actual)
    return {
        "available": True,
        "from": first_monday.date().isoformat(),
        "through": last_sunday.date().isoformat(),
        "weekdays_n": [26] * 7,
        "prediction_count": len(tested),
        "brier_score": score,
        "brier_benchmark": reference,
        "brier_skill": 1 - score / reference if reference else None,
        "test_rows": rows,
    }


def record_shadow_quality(
    root: Path,
    frame: pd.DataFrame,
    weights: dict[str, float],
    dashboard: dict[str, Any],
    source_status: dict[str, Any],
) -> None:
    append_immutable(
        root / "data/research/shadow_definitions.jsonl", SHADOW_DEFINITION, ["definition_id"]
    )
    result = balanced_backtest(frame, weights)
    quality = None
    if result["available"]:
        components = dashboard["scores"]["evidence_components"]
        quality = evidence_quality(
            components["data_quality"],
            dashboard["analog_summary"],
            {"7d": result},
            stability=components["stability"],
            missing_sources=source_status["missing_validated_sources"],
            critical_error=source_status["critical_error"],
        )
    append_immutable(
        root / "data/research/shadow_quality.jsonl",
        {
            "definition_id": SHADOW_DEFINITION["definition_id"],
            "run_at_utc": dashboard["generated_at_utc"],
            "data_cutoff_utc": dashboard["data_cutoff_utc"],
            "original_quality": dashboard["scores"]["evidence_quality"],
            "alternative_quality": quality["score"] if quality else None,
            "alternative_caps": quality["caps"] if quality else [],
            "evaluation": result,
        },
        ["definition_id", "run_at_utc"],
    )
