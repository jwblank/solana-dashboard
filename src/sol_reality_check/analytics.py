from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm


def pct_change(series: pd.Series, days: int) -> pd.Series:
    return series / series.shift(days) - 1


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("date").reset_index(drop=True).copy()
    out["sol_return_1d"] = pct_change(out["sol_close"], 1)
    out["sol_return_7d"] = pct_change(out["sol_close"], 7)
    out["sol_return_30d"] = pct_change(out["sol_close"], 30)
    out["btc_return_7d"] = pct_change(out["btc_close"], 7)
    out["btc_return_30d"] = pct_change(out["btc_close"], 30)
    out["relative_strength_btc_7d"] = out["sol_return_7d"] - out["btc_return_7d"]
    out["relative_strength_btc_30d"] = out["sol_return_30d"] - out["btc_return_30d"]
    out["price_vs_sma50"] = out["sol_close"] / out["sol_close"].rolling(50).mean() - 1
    out["price_vs_sma200"] = out["sol_close"] / out["sol_close"].rolling(200).mean() - 1
    log_ret = np.log(out["sol_close"]).diff()
    out["realized_volatility_30d"] = log_ret.rolling(30).std() * math.sqrt(365)
    out["drawdown_90d"] = out["sol_close"] / out["sol_close"].rolling(90).max() - 1
    out["volume_ratio_7d_30d"] = (
        out["sol_volume"].rolling(7).mean() / out["sol_volume"].rolling(30).mean()
    )
    out["dex_volume_ratio_7d_30d"] = (
        out["dex_volume"].rolling(7).sum() / out["dex_volume"].rolling(30).mean()
    )
    out["dex_volume_change_30d"] = pct_change(out["dex_volume"].rolling(7).sum(), 30)
    out["fees_ratio_7d_30d"] = out["fees"].rolling(7).sum() / out["fees"].rolling(30).mean()
    out["tvl_change_7d"] = pct_change(out["tvl"], 7)
    out["tvl_change_30d"] = pct_change(out["tvl"], 30)
    out["stablecoin_change_7d"] = pct_change(out["stablecoins"], 7)
    out["stablecoin_change_30d"] = pct_change(out["stablecoins"], 30)
    return out


def robust_z_scores(
    df: pd.DataFrame, columns: list[str], window: int = 730, min_obs: int = 180
) -> pd.DataFrame:
    scores = pd.DataFrame(index=df.index)
    for column in columns:
        values = df[column]
        med = values.shift(1).rolling(window, min_periods=min_obs).median()
        mad = (values.shift(1) - med).abs().rolling(window, min_periods=min_obs).median()
        safe_mad = mad.mask(mad == 0)
        z = 0.6745 * (values - med) / safe_mad
        scores[f"{column}__z"] = z.clip(-4, 4)
        scores[f"{column}__score"] = (50 + 12.5 * scores[f"{column}__z"]).clip(0, 100)
    return scores


def weighted_average(
    values: dict[str, float | None], weights: dict[str, float]
) -> tuple[float | None, list[str]]:
    present: dict[str, float] = {}
    for key in weights:
        value = values.get(key)
        if value is not None and not np.isnan(float(value)):
            present[key] = float(value)
    if not present:
        return None, list(weights)
    weight_sum = sum(weights[k] for k in present)
    score = sum(present[k] * weights[k] for k in present) / weight_sum
    missing = [k for k in weights if k not in present]
    return round(score, 2), missing


def score_label(score: float | None) -> str:
    if score is None:
        return "geen gevalideerde conclusie"
    if score <= 34:
        return "sterk negatief"
    if score <= 44:
        return "negatief"
    if score <= 55:
        return "neutraal of gemengd"
    if score <= 65:
        return "positief"
    return "sterk positief"


def evidence_label(score: float) -> str:
    if score <= 39:
        return "zwak onderbouwd"
    if score <= 59:
        return "beperkt onderbouwd"
    if score <= 74:
        return "redelijk onderbouwd"
    if score <= 89:
        return "sterk onderbouwd"
    return "uitzonderlijk sterk onderbouwd"


def regime(
    price_strength: float | None, network_usage: float | None, capital: float | None
) -> tuple[str, str]:
    if price_strength is None or network_usage is None or capital is None:
        return "insufficient_data", "Er is onvoldoende data voor een gevalideerd regime."
    confirmation = 0.55 * network_usage + 0.45 * capital
    if 45 <= price_strength <= 55 or 45 <= confirmation <= 55:
        return "mixed", "De indicatoren geven nog geen overtuigende gezamenlijke richting."
    if price_strength >= 55 and confirmation >= 55:
        return (
            "confirmed_trend",
            "De koers is sterk en wordt bevestigd door netwerkgebruik en kapitaal.",
        )
    if price_strength >= 55 and confirmation < 45:
        return (
            "fragile_rally",
            "De koers stijgt, maar de onderliggende data bevestigt de beweging onvoldoende.",
        )
    if price_strength < 45 and confirmation >= 55:
        return (
            "building_under_surface",
            "De koers is nog zwak, terwijl netwerkgebruik en kapitaal al verbeteren.",
        )
    return "risk_regime", "Zowel de koers als de onderliggende bevestiging is zwak."


def find_analogs(
    df: pd.DataFrame,
    as_of_index: int,
    feature_weights: dict[str, float],
    horizon: int,
    max_count: int = 40,
    min_spacing: int = 7,
) -> pd.DataFrame:
    current = df.iloc[as_of_index]
    candidates = df.iloc[: max(0, as_of_index - horizon)].copy()
    distances: list[tuple[int, float, float]] = []
    for idx, row in candidates.iterrows():
        numerator = 0.0
        denom = 0.0
        for feature, weight in feature_weights.items():
            a = current.get(f"{feature}__z")
            b = row.get(f"{feature}__z")
            if pd.notna(a) and pd.notna(b):
                numerator += weight * float(a - b) ** 2
                denom += weight
        if denom / sum(feature_weights.values()) >= 0.8:
            distance = math.sqrt(numerator / denom)
            similarity = 100 * math.exp(-0.5 * distance**2)
            distances.append((idx, distance, similarity))
    selected: list[tuple[int, float, float]] = []
    for item in sorted(distances, key=lambda x: (x[1], x[0])):
        if all(abs(item[0] - other[0]) >= min_spacing for other in selected):
            selected.append(item)
        if len(selected) >= max_count:
            break
    analogs = df.loc[[x[0] for x in selected], ["date", "sol_close"]].copy()
    analogs["distance"] = [x[1] for x in selected]
    analogs["similarity"] = [x[2] for x in selected]
    analogs[f"return_{horizon}d"] = [
        df.loc[idx + horizon, "sol_close"] / df.loc[idx, "sol_close"] - 1 for idx, _, _ in selected
    ]
    return analogs


def wilson_interval(
    successes: int, n: int, confidence: float = 0.95
) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    z = norm.ppf(1 - (1 - confidence) / 2)
    phat = successes / n
    denom = 1 + z**2 / n
    centre = (phat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt((phat * (1 - phat) + z**2 / (4 * n)) / n) / denom
    return centre - margin, centre + margin


def analog_summary(analogs: pd.DataFrame, horizon: int) -> dict[str, Any]:
    col = f"return_{horizon}d"
    values = analogs[col].dropna()
    n = int(values.shape[0])
    successes = int((values > 0).sum())
    low, high = wilson_interval(successes, n)
    return {
        "horizon_days": horizon,
        "count": n,
        "positive_count": successes,
        "positive_frequency": round(successes / n, 4) if n else None,
        "wilson_low": round(low, 4) if low is not None else None,
        "wilson_high": round(high, 4) if high is not None else None,
        "median_return": round(float(values.median()), 4) if n else None,
        "mean_return": round(float(values.mean()), 4) if n else None,
        "p10": round(float(values.quantile(0.10)), 4) if n else None,
        "p25": round(float(values.quantile(0.25)), 4) if n else None,
        "p75": round(float(values.quantile(0.75)), 4) if n else None,
        "p90": round(float(values.quantile(0.90)), 4) if n else None,
        "worst": round(float(values.min()), 4) if n else None,
        "best": round(float(values.max()), 4) if n else None,
        "median_similarity": round(float(analogs["similarity"].median()), 2) if n else None,
    }


@dataclass
class BacktestResult:
    predictions: pd.DataFrame
    summary: dict[str, Any]


def brier_score(prob: pd.Series, actual: pd.Series) -> float:
    return float(((prob - actual) ** 2).mean())


def run_backtest(
    df: pd.DataFrame, feature_weights: dict[str, float], horizons: list[int], stride: int = 7
) -> BacktestResult:
    rows: list[dict[str, Any]] = []
    min_start = 365
    for horizon in horizons:
        for idx in range(min_start, len(df) - horizon, stride):
            analogs = find_analogs(df, idx, feature_weights, horizon)
            summary = analog_summary(analogs, horizon)
            if summary["count"] < 10:
                continue
            actual_return = df.loc[idx + horizon, "sol_close"] / df.loc[idx, "sol_close"] - 1
            rows.append(
                {
                    "date": df.loc[idx, "date"],
                    "horizon": horizon,
                    "probability": summary["positive_frequency"],
                    "predicted_direction": summary["positive_frequency"] >= 0.5,
                    "actual_positive": actual_return > 0,
                    "actual_return": actual_return,
                    "median_predicted_return": summary["median_return"],
                    "regime": df.loc[idx, "regime"],
                }
            )
    pred = pd.DataFrame(rows)
    summary_by_horizon: dict[str, Any] = {}
    for horizon in horizons:
        h = pred[pred["horizon"] == horizon]
        if h.empty:
            summary_by_horizon[f"{horizon}d"] = {"prediction_count": 0}
            continue
        actual = h["actual_positive"].astype(float)
        probs = h["probability"].astype(float)
        base = actual.expanding().mean().shift(1).fillna(actual.mean())
        brier = brier_score(probs, actual)
        benchmark = brier_score(base, actual)
        accuracy = float((h["predicted_direction"] == h["actual_positive"]).mean())
        always_up = float(actual.mean())
        summary_by_horizon[f"{horizon}d"] = {
            "prediction_count": int(len(h)),
            "directional_accuracy": round(accuracy, 4),
            "always_up_accuracy": round(always_up, 4),
            "directional_lift_vs_always_up": round(accuracy - always_up, 4),
            "brier_score": round(brier, 4),
            "brier_benchmark": round(benchmark, 4),
            "brier_skill": round(1 - brier / benchmark, 4) if benchmark else None,
            "calibration_error": round(float(abs(probs.mean() - actual.mean())), 4),
            "interval_coverage_10_90": None,
            "non_overlapping_prediction_count": int(len(h.iloc[::horizon])),
        }
    return BacktestResult(predictions=pred, summary=summary_by_horizon)


def evidence_quality(
    data_quality: float,
    analogs: dict[str, Any],
    backtest: dict[str, Any],
    stability: float,
    missing_sources: int = 0,
    critical_error: bool = False,
) -> dict[str, Any]:
    sample = min(100.0, 100 * (analogs.get("count", 0) / 40))
    oos = 50.0
    h7 = backtest.get("7d", {})
    if h7.get("prediction_count", 0):
        skill = h7.get("brier_skill") or 0
        oos = max(0.0, min(100.0, 55 + 400 * skill))
    similarity = min(100.0, float(analogs.get("median_similarity") or 0))
    raw = 0.25 * data_quality + 0.15 * sample + 0.30 * oos + 0.20 * stability + 0.10 * similarity
    caps: list[str] = []
    if analogs.get("count", 0) < 20:
        raw = min(raw, 45)
        caps.append("Minder dan 20 effectieve analogieën")
    if (h7.get("brier_skill") or 0) <= 0:
        raw = min(raw, 55)
        caps.append("Voorspelkwaliteit ≤ 0")
    if h7.get("prediction_count", 0) < 100:
        raw = min(raw, 55)
        caps.append("Minder dan 100 out-of-sample voorspellingen")
    if missing_sources >= 2:
        raw = 0
        caps.append("Twee of meer ontbrekende hoofdbronnen")
    if critical_error:
        raw = 0
        caps.append("Kritieke datavalidatiefout")
    return {
        "score": round(raw, 2),
        "label": evidence_label(raw),
        "components": {
            "data_quality": round(data_quality, 2),
            "sample_adequacy": round(sample, 2),
            "out_of_sample_quality": round(oos, 2),
            "stability": round(stability, 2),
            "analog_similarity": round(similarity, 2),
        },
        "caps": caps,
    }
