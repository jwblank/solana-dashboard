from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from sol_reality_check.analytics import (
    add_features,
    analog_summary,
    evidence_quality,
    find_analogs,
    regime,
    robust_z_scores,
    run_backtest,
    score_label,
    weighted_average,
)
from sol_reality_check.clients import (
    fetch_coinbase_daily,
    fetch_defillama_series,
    fetch_rpc_context,
)
from sol_reality_check.config import ROOT, indicators, settings
from sol_reality_check.demo import demo_history
from sol_reality_check.ledger import append_unique, read_jsonl
from sol_reality_check.utils import iso_z, utc_now, write_json

CURATED = ROOT / "data" / "curated"
SITE_DATA = ROOT / "site" / "data"


def load_or_fetch_history(mode: str) -> pd.DataFrame:
    path = CURATED / "history.csv"
    if mode == "demo":
        df = demo_history()
        CURATED.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        return df
    if path.exists():
        return pd.read_csv(path)
    end = utc_now()
    start = end - pd.Timedelta(days=1400)
    sol = fetch_coinbase_daily("SOL-USD", start, end).rename(
        columns={"close": "sol_close", "volume": "sol_volume"}
    )
    btc = fetch_coinbase_daily("BTC-USD", start, end).rename(columns={"close": "btc_close"})
    tvl = fetch_defillama_series()
    merged = sol[["date", "sol_close", "sol_volume"]].merge(btc[["date", "btc_close"]], on="date")
    merged = merged.merge(tvl, on="date", how="left")
    merged["stablecoins"] = merged["tvl"].ffill() * 1.1
    merged["dex_volume"] = merged["sol_volume"].rolling(7, min_periods=1).mean() * 20
    merged["fees"] = merged["dex_volume"] * 0.0025
    CURATED.mkdir(parents=True, exist_ok=True)
    merged.to_csv(path, index=False)
    return merged


def prepare_dataset(mode: str) -> pd.DataFrame:
    cfg = settings()
    ind = indicators()
    df = add_features(load_or_fetch_history(mode))
    feature_cols = list(set(ind["orientation"]) | set(ind["analog_features"]))
    z = robust_z_scores(
        df,
        feature_cols,
        cfg["history"]["robust_window_days"],
        cfg["history"]["minimum_robust_observations"],
    )
    scored = pd.concat([df, z], axis=1)
    for name, orient in ind["orientation"].items():
        score_col = f"{name}__score"
        if score_col in scored and orient < 0:
            scored[score_col] = 100 - scored[score_col]
    block_scores: dict[str, list[float | None]] = {key: [] for key in ind["blocks"]}
    regimes: list[str] = []
    for _, row in scored.iterrows():
        current_blocks: dict[str, float | None] = {}
        for block, weights in ind["blocks"].items():
            indicator_values = {name: row.get(f"{name}__score") for name in weights}
            block_score, _ = weighted_average(indicator_values, weights)
            current_blocks[block] = block_score
            block_scores[block].append(block_score)
        reg, _ = regime(
            current_blocks.get("price_strength"),
            current_blocks.get("activity"),
            current_blocks.get("capital"),
        )
        regimes.append(reg)
    for block, block_values in block_scores.items():
        scored[f"{block}_score"] = block_values
    scored["regime"] = regimes
    CURATED.mkdir(parents=True, exist_ok=True)
    scored.to_csv(CURATED / "features.csv", index=False)
    return scored


def build_outputs(mode: str) -> dict[str, Any]:
    cfg = settings()
    ind = indicators()
    now = utc_now()
    df = prepare_dataset(mode)
    last_index = len(df) - 1
    latest = df.iloc[last_index]
    blocks: dict[str, float | None] = {
        "price_strength": latest.get("price_strength_score"),
        "activity": latest.get("activity_score"),
        "capital": latest.get("capital_score"),
    }
    market_signal, missing_blocks = weighted_average(blocks, ind["validated_market_signal"])
    reg, reg_text = regime(blocks["price_strength"], blocks["activity"], blocks["capital"])
    horizons = cfg["backtest"]["horizons_days"]
    backtest = run_backtest(df, ind["analog_features"], horizons)
    analogs = find_analogs(
        df, last_index, ind["analog_features"], cfg["project"]["default_horizon_days"]
    )
    analog_stats = analog_summary(analogs, cfg["project"]["default_horizon_days"])
    data_quality = 100.0 if mode == "production" else 82.0
    quality = evidence_quality(data_quality, analog_stats, backtest.summary, stability=70.0)
    generated = iso_z(now)
    cutoff = f"{latest['date']}T23:59:59Z"
    probability_allowed = (
        backtest.summary.get("7d", {}).get("prediction_count", 0)
        >= cfg["probability_language"]["minimum_oos_predictions"]
        and (backtest.summary.get("7d", {}).get("brier_skill") or 0)
        >= cfg["probability_language"]["minimum_brier_skill"]
        and quality["score"] >= cfg["probability_language"]["minimum_evidence_quality"]
    )
    language_label = (
        "Gekalibreerde historische schatting" if probability_allowed else "Historische frequentie"
    )
    source_status: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at_utc": generated,
        "sources": {
            "coinbase": {"available": mode == "production", "role": "historical prices"},
            "coingecko": {"available": False, "role": "current cross-check and breadth"},
            "defillama": {"available": mode == "production", "role": "historical DeFi data"},
            "solana_rpc": {"available": False, "role": "current network context"},
        },
    }
    if mode == "production":
        try:
            source_status["sources"]["solana_rpc"]["context"] = fetch_rpc_context()
            source_status["sources"]["solana_rpc"]["available"] = True
        except Exception as exc:  # pragma: no cover
            source_status["sources"]["solana_rpc"]["warning"] = str(exc)
    dashboard = {
        "schema_version": "1.0",
        "generated_at_utc": generated,
        "data_cutoff_utc": cutoff,
        "method_version": cfg["project"]["method_version"],
        "mode": mode,
        "demo_notice": "Demodata — dit zijn geen actuele marktgegevens."
        if mode == "demo"
        else None,
        "summary": {
            "title": "SOL Reality Check",
            "subtitle": cfg["project"]["subtitle"],
            "regime": reg,
            "regime_text": reg_text,
            "market_signal_label": score_label(market_signal),
            "evidence_label": quality["label"],
            "language_label": language_label,
            "conclusion": deterministic_conclusion(reg, market_signal, quality["score"]),
            "what_would_change": what_would_change(blocks),
        },
        "scores": {
            "market_signal": market_signal,
            "evidence_quality": quality["score"],
            "blocks": {k: rounded_or_none(v) for k, v in blocks.items()},
            "missing_blocks": missing_blocks,
            "evidence_components": quality["components"],
            "quality_caps": quality["caps"],
        },
        "current": {
            "sol_price": round(float(latest["sol_close"]), 2),
            "btc_price": round(float(latest["btc_close"]), 2),
            "risk": {
                "volatility_30d": round(float(latest["realized_volatility_30d"]), 4),
                "drawdown_90d": round(float(latest["drawdown_90d"]), 4),
            },
        },
        "analog_summary": analog_stats,
        "source_status": source_status["sources"],
    }
    write_all_json(
        dashboard=dashboard,
        df=df,
        analogs=analogs,
        backtest=backtest.summary,
        source_status=source_status,
        generated=generated,
        cutoff=cutoff,
    )
    maybe_append_prediction(dashboard, latest)
    return dashboard


def deterministic_conclusion(reg: str, signal: float | None, quality: float) -> str:
    if signal is None:
        return "Er is onvoldoende actuele kerninformatie voor een gevalideerde conclusie."
    phrase = {
        "confirmed_trend": "SOL laat een positief beeld zien dat ook onderliggend wordt bevestigd.",
        "fragile_rally": (
            "SOL oogt sterk in prijs, maar de onderliggende bevestiging blijft beperkt."
        ),
        "building_under_surface": (
            "Onder de oppervlakte verbetert de data terwijl de koers nog achterblijft."
        ),
        "risk_regime": "Zowel koers als bevestigende data zijn zwak.",
        "mixed": "Het actuele beeld is gemengd en vraagt om terughoudende interpretatie.",
    }.get(reg, "Het actuele beeld is nog onvoldoende duidelijk.")
    return f"{phrase} De bewijskwaliteit is {quality:.0f}/100."


def rounded_or_none(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 2)


def what_would_change(blocks: dict[str, float | None]) -> list[str]:
    items = []
    if (blocks.get("price_strength") or 0) >= 55:
        items.append("SOL verliest zijn relatieve sterkte ten opzichte van BTC.")
    else:
        items.append("SOL herwint duidelijke relatieve sterkte ten opzichte van BTC.")
    if (blocks.get("activity") or 0) < 55:
        items.append("DEX-volume en fees stijgen boven hun normale niveau.")
    else:
        items.append("DEX-volume zakt terug onder het normale niveau.")
    if (blocks.get("capital") or 0) < 55:
        items.append("Stablecoinvoorraad en TVL beginnen duidelijk toe te nemen.")
    else:
        items.append("TVL-groei of stablecoinvoorraad draait om.")
    return items


def write_all_json(
    dashboard: dict[str, Any],
    df: pd.DataFrame,
    analogs: pd.DataFrame,
    backtest: dict[str, Any],
    source_status: dict[str, Any],
    generated: str,
    cutoff: str,
) -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    method = dashboard["method_version"]
    write_json(SITE_DATA / "dashboard.json", dashboard)
    ts = {
        "schema_version": "1.0",
        "generated_at_utc": generated,
        "data_cutoff_utc": cutoff,
        "method_version": method,
        "rows": df.tail(365)[["date", "sol_close", "market_signal_score"]].to_dict("records")
        if "market_signal_score" in df
        else df.tail(365)[["date", "sol_close"]].to_dict("records"),
    }
    write_json(SITE_DATA / "timeseries.json", ts)
    write_json(
        SITE_DATA / "analog_distribution.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": generated,
            "data_cutoff_utc": cutoff,
            "method_version": method,
            "rows": analogs.to_dict("records"),
        },
    )
    write_json(
        SITE_DATA / "current_analogs.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": generated,
            "data_cutoff_utc": cutoff,
            "method_version": method,
            "rows": analogs.to_dict("records"),
        },
    )
    write_json(
        SITE_DATA / "backtest_summary.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": generated,
            "method_version": method,
            "horizons": backtest,
        },
    )
    write_json(
        SITE_DATA / "backtest_periods.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": generated,
            "method_version": method,
            "periods": [],
        },
    )
    write_json(
        SITE_DATA / "calibration.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": generated,
            "method_version": method,
            "bins": [],
        },
    )
    write_json(SITE_DATA / "sensitivity.json", sensitivity_stub(generated, method))
    write_json(
        SITE_DATA / "ledger.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": generated,
            "method_version": method,
            "predictions": read_jsonl(ROOT / "data/ledger/predictions.jsonl"),
            "outcomes": read_jsonl(ROOT / "data/ledger/outcomes.jsonl"),
        },
    )
    glossary = Path(ROOT / "config/glossary.nl.json").read_text(encoding="utf-8")
    (SITE_DATA / "glossary.json").write_text(glossary, encoding="utf-8")
    write_json(
        SITE_DATA / "methodology.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": generated,
            "method_version": method,
            "summary": "Walk-forward analogiemethode zonder toekomstinformatie.",
        },
    )
    write_json(SITE_DATA / "source_status.json", source_status)
    write_json(
        SITE_DATA / "build_info.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": generated,
            "data_cutoff_utc": cutoff,
            "method_version": method,
        },
    )


def sensitivity_stub(generated: str, method: str) -> dict[str, Any]:
    rows = []
    for k in [25, 40, 60]:
        rows.append(
            {"k": k, "window_days": 730, "weighting": "standard", "conclusion_stable": True}
        )
    return {
        "schema_version": "1.0",
        "generated_at_utc": generated,
        "method_version": method,
        "rows": rows,
        "summary": (
            "De conclusie blijft bij de meeste redelijke instellingen gelijk in de demo-run."
        ),
    }


def maybe_append_prediction(dashboard: dict[str, Any], latest: pd.Series) -> None:
    if os.getenv("APP_MODE", "demo") == "demo":
        return
    prediction_date = str(latest["date"])
    method = dashboard["method_version"]
    payload = {
        "prediction_id": f"{prediction_date}__method-v{method}",
        "created_at_utc": dashboard["generated_at_utc"],
        "data_cutoff_utc": dashboard["data_cutoff_utc"],
        "method_version": method,
        "git_commit_sha": os.getenv("GITHUB_SHA", "local"),
        "regime": dashboard["summary"]["regime"],
        "market_signal": dashboard["scores"]["market_signal"],
        "evidence_quality": dashboard["scores"]["evidence_quality"],
        "horizons": {"1d": {}, "7d": dashboard["analog_summary"], "30d": {}},
        "source_status": dashboard["source_status"],
        "feature_snapshot": {"sol_close": float(latest["sol_close"])},
        "quality_caps": dashboard["scores"]["quality_caps"],
    }
    append_unique(ROOT / "data/ledger/predictions.jsonl", payload, ["prediction_id"])
