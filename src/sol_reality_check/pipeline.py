from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
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
    MAX_TRUSTED_DAILY_PRICE_CHANGE,
    ApiError,
    fetch_ccxt_consensus_daily,
    fetch_coinbase_daily,
    fetch_coingecko_breadth,
    fetch_coingecko_current,
    fetch_defillama_series,
    fetch_rpc_context,
    repair_daily_price_outliers,
)
from sol_reality_check.config import ROOT, indicators, load_yaml, settings
from sol_reality_check.demo import demo_history
from sol_reality_check.ledger import append_unique, read_jsonl
from sol_reality_check.llm_interpretation import build_interpretation
from sol_reality_check.utils import iso_z, utc_now, write_json

CURATED = ROOT / "data" / "curated"
SITE_DATA = ROOT / "site" / "data"
LOGGER = logging.getLogger(__name__)
PRICE_METADATA_COLUMNS = [
    "sol_price_source_count",
    "sol_price_sources",
    "btc_price_source_count",
    "btc_price_sources",
]
MAX_ALLOWED_CACHE_PRICE_BREAK = 0.40
SIGNAL_RESEARCH_PATH = CURATED / "signaalonderzoek.parquet"
SIGNAL_RESEARCH_LATEST_PATH = SITE_DATA / "signaalonderzoek.json"
OVERVIEW_PATH = SITE_DATA / "overview.json"
OVERVIEW_HISTORY_PATH = SITE_DATA / "overview_history.json"
SIGNAL_RESEARCH_KEY = "run_at_utc"
SCORE_CHANGE_THRESHOLDS = {
    "unchanged": 0.5,
    "light": 2.0,
    "clear": 5.0,
}
MATURITY_THRESHOLDS = [
    (0, "Startfase"),
    (30, "Opbouwfase"),
    (100, "Eerste structurele evaluatie mogelijk"),
    (250, "Volwassen publiek trackrecord"),
]
WATERFALL_RESIDUAL_VISIBILITY_THRESHOLD = 0.05
WATERFALL_RECONCILIATION_TOLERANCE = 1e-6
DRIVER_ORDER = [
    ("price_strength", "Koerskracht", "price_strength_score"),
    ("network_usage", "Netwerkgebruik", "network_usage_score"),
    ("capital_flows", "Kapitaalstromen", "capital_flows_score"),
    ("ecosystem_breadth", "Ecosysteembreedte", "ecosystem_breadth_score"),
]
SIGNAL_RESEARCH_COLUMNS = [
    "run_at_utc",
    "data_cutoff_utc",
    "method_version",
    "mode",
    "sol_price",
    "btc_price",
    "sol_live_price",
    "btc_live_price",
    "current_strength_score",
    "support_score",
    "price_strength_score",
    "network_usage_score",
    "capital_flows_score",
    "ecosystem_breadth_score",
    "regime",
    "regime_title",
    "sol_return_1d",
    "sol_return_7d",
    "sol_return_30d",
    "btc_return_7d",
    "btc_return_30d",
    "relative_strength_btc_7d",
    "relative_strength_btc_30d",
    "price_vs_sma50",
    "price_vs_sma200",
    "realized_volatility_30d",
    "drawdown_90d",
    "dex_volume_ratio_7d_30d",
    "dex_volume_change_30d",
    "fees_ratio_7d_30d",
    "tvl_change_7d",
    "tvl_change_30d",
    "stablecoin_change_7d",
    "stablecoin_change_30d",
    "price_strength_weight",
    "network_usage_weight",
    "capital_flows_weight",
    "ecosystem_breadth_weight",
    "price_strength_contribution",
    "network_usage_contribution",
    "capital_flows_contribution",
    "ecosystem_breadth_contribution",
]


def load_or_fetch_history(mode: str) -> pd.DataFrame:
    path = CURATED / "history.csv"
    if mode == "demo":
        df = demo_history()
        CURATED.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        return df
    if path.exists():
        if mode != "production":
            cached = repair_history_prices(pd.read_csv(path))
            cached.to_csv(path, index=False)
            return cached
        raw_cache = pd.read_csv(path)
        cache_ok, cache_reason = production_history_cache_is_usable(raw_cache)
        cached = repair_history_prices(raw_cache) if cache_ok else None
        if not cache_ok:
            LOGGER.warning("Ignoring production history cache: %s", cache_reason)
        try:
            refreshed = fetch_history_window(cached)
            refreshed.to_csv(path, index=False)
            return refreshed
        except ApiError:
            if cached is not None:
                return cached
            raise
    end = last_completed_utc_day_end()
    start = end - pd.Timedelta(days=1400)
    merged = fetch_history_window(None, start=start, end=end)
    CURATED.mkdir(parents=True, exist_ok=True)
    merged.to_csv(path, index=False)
    return merged


def fetch_history_window(
    existing: pd.DataFrame | None,
    start: datetime | pd.Timestamp | None = None,
    end: datetime | pd.Timestamp | None = None,
) -> pd.DataFrame:
    end = end or last_completed_utc_day_end()
    end_date = pd.Timestamp(end).date().isoformat()
    if existing is not None and not existing.empty:
        last_date = pd.to_datetime(existing["date"].max(), utc=True)
        start = max(last_date - pd.Timedelta(days=7), end - pd.Timedelta(days=90))
    start = start or end - pd.Timedelta(days=1400)
    sol = fetch_price_history("sol", "SOL-USD", start, end).rename(
        columns={
            "close": "sol_close",
            "volume": "sol_volume",
            "source_count": "sol_price_source_count",
            "outlier_count": "sol_price_outlier_count",
            "sources": "sol_price_sources",
        }
    )
    btc = fetch_price_history("btc", "BTC-USD", start, end).rename(
        columns={
            "close": "btc_close",
            "source_count": "btc_price_source_count",
            "outlier_count": "btc_price_outlier_count",
            "sources": "btc_price_sources",
        }
    )
    price_status = {
        "sol": sol.attrs.get("price_source_status", {}),
        "btc": btc.attrs.get("price_source_status", {}),
    }
    defi = fetch_defillama_series()
    merged = sol[available_columns(sol, [
        "date",
        "sol_close",
        "sol_volume",
        "sol_price_source_count",
        "sol_price_outlier_count",
        "sol_price_sources",
    ])].merge(
        btc[available_columns(btc, [
            "date",
            "btc_close",
            "btc_price_source_count",
            "btc_price_outlier_count",
            "btc_price_sources",
        ])],
        on="date",
    )
    merged = merged.merge(defi, on="date", how="left")
    for column in ["tvl", "stablecoins", "dex_volume", "fees"]:
        if column not in merged:
            merged[column] = pd.NA
    if existing is not None and not existing.empty:
        merged = pd.concat([existing, merged], ignore_index=True)
        merged = merged.drop_duplicates("date", keep="last")
    merged = merged[merged["date"] < end_date]
    trusted_price_dates = trusted_dates_from_price_sources(sol, btc)
    merged = repair_history_prices(merged.sort_values("date"), trusted_price_dates)
    assert_no_extreme_price_breaks(merged, trusted_price_dates)
    merged.attrs["price_source_status"] = price_status
    return merged


def production_history_cache_is_usable(df: pd.DataFrame) -> tuple[bool, str]:
    missing = [column for column in PRICE_METADATA_COLUMNS if column not in df]
    if missing:
        return False, f"missing price source metadata: {', '.join(missing)}"
    if df.empty:
        return False, "empty history cache"
    for column in ["sol_close", "btc_close"]:
        if column not in df:
            return False, f"missing {column}"
    break_reason = extreme_price_break_reason(df, trusted_dates_from_history(df))
    if break_reason:
        return False, break_reason
    return True, ""


def extreme_price_break_reason(
    df: pd.DataFrame,
    trusted_price_dates: dict[str, set[str]] | None = None,
    threshold: float = MAX_ALLOWED_CACHE_PRICE_BREAK,
) -> str:
    ordered = df.sort_values("date").reset_index(drop=True)
    trusted_price_dates = trusted_price_dates or {}
    for column in ["sol_close", "btc_close"]:
        if column not in ordered:
            continue
        changes = pd.to_numeric(ordered[column], errors="coerce").pct_change().abs()
        bad = changes[changes > threshold]
        trusted_dates = trusted_price_dates.get(column, set())
        for idx, change in bad.items():
            row_idx = int(idx)
            current_date = str(ordered.at[row_idx, "date"])
            if current_date in trusted_dates and float(change) <= MAX_TRUSTED_DAILY_PRICE_CHANGE:
                LOGGER.warning(
                    "Allowing large %s move of %.1f%% on %s because it is backed by "
                    "trusted price-source metadata.",
                    column,
                    float(change) * 100,
                    current_date,
                )
                continue
            return (
                f"{column} daily break {change:.1%} between "
                f"{ordered.at[row_idx - 1, 'date']} and {ordered.at[row_idx, 'date']}"
            )
    return ""


def assert_no_extreme_price_breaks(
    df: pd.DataFrame,
    trusted_price_dates: dict[str, set[str]] | None = None,
) -> None:
    reason = extreme_price_break_reason(df, trusted_price_dates)
    if reason:
        raise ApiError(f"Untrusted price history after rebuild: {reason}")


def trusted_dates_from_price_sources(
    sol: pd.DataFrame,
    btc: pd.DataFrame,
) -> dict[str, set[str]]:
    trusted: dict[str, set[str]] = {}
    if str(sol.attrs.get("price_source_status", {}).get("provider", "")).startswith(
        "CCXT consensus"
    ):
        trusted["sol_close"] = set(sol["date"].astype(str))
    if str(btc.attrs.get("price_source_status", {}).get("provider", "")).startswith(
        "CCXT consensus"
    ):
        trusted["btc_close"] = set(btc["date"].astype(str))
    return trusted


def available_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column in df]


def fetch_price_history(
    asset: str,
    coinbase_product_id: str,
    start: datetime | pd.Timestamp,
    end: datetime | pd.Timestamp,
) -> pd.DataFrame:
    cfg = settings()
    source_cfg = load_yaml("config/sources.yml")
    ccxt_cfg = source_cfg.get("sources", {}).get("ccxt", {})
    try:
        frame = fetch_ccxt_consensus_daily(
            asset=asset,
            exchange_configs=ccxt_cfg.get("exchanges", []),
            start=pd.Timestamp(start).to_pydatetime(),
            end=pd.Timestamp(end).to_pydatetime(),
            min_sources=int(ccxt_cfg.get("min_sources", 2)),
            max_deviation_pct=float(ccxt_cfg.get("max_exchange_deviation_pct", 5.0)),
        )
        assert_price_coverage(
            frame,
            start,
            end,
            min_coverage_ratio=float(ccxt_cfg.get("min_coverage_ratio", 0.8)),
            min_required_rows=minimum_price_history_rows(cfg),
        )
        frame = fill_price_history_gaps_with_coinbase(
            frame,
            coinbase_product_id,
            start,
            end,
        )
        frame.attrs["price_source_status"] = {
            "provider": frame.attrs.get("provider", "CCXT consensus"),
            **frame.attrs.get("ccxt_status", {}),
            **frame.attrs.get("coinbase_gap_fill_status", {}),
        }
        return frame
    except Exception as exc:  # pragma: no cover - exchange/network dependent
        frame = fetch_coinbase_daily(
            coinbase_product_id,
            pd.Timestamp(start).to_pydatetime(),
            pd.Timestamp(end).to_pydatetime(),
        )
        frame.attrs["price_source_status"] = {
            "provider": "Coinbase fallback",
            "asset": asset.upper(),
            "available": False,
            "fallback_used": True,
            "warning": str(exc),
            "rows": len(frame),
            "price_breakdown": coinbase_fallback_breakdown(frame, asset),
        }
        frame["source_count"] = 1
        frame["outlier_count"] = 0
        frame["sources"] = "coinbase"
        return frame


def coinbase_fallback_breakdown(frame: pd.DataFrame, asset: str) -> dict[str, Any]:
    latest = frame.sort_values("date").iloc[-1]
    return {
        "asset": asset.upper(),
        "date": str(latest["date"]),
        "method": "Coinbase fallback",
        "used_close": round(float(latest["close"]), 8),
        "source_count": 1,
        "outlier_count": 0,
        "exchange_prices": [
            {
                "exchange": "coinbase",
                "symbol": str(latest.get("asset", asset.upper())) + "-USD",
                "close": round(float(latest["close"]), 8),
                "used": True,
                "deviation_pct": 0.0,
            }
        ],
    }


def fill_price_history_gaps_with_coinbase(
    frame: pd.DataFrame,
    coinbase_product_id: str,
    start: datetime | pd.Timestamp,
    end: datetime | pd.Timestamp,
) -> pd.DataFrame:
    gap_start = first_missing_daily_date(frame, start, end)
    if gap_start is None:
        return frame
    coinbase = fetch_coinbase_daily(
        coinbase_product_id,
        pd.Timestamp(gap_start, tz=UTC).to_pydatetime(),
        pd.Timestamp(end).to_pydatetime(),
    )
    coinbase = coinbase.copy()
    coinbase["source_count"] = 1
    coinbase["outlier_count"] = 0
    coinbase["sources"] = "coinbase"
    combined = pd.concat(
        [
            frame[frame["date"] < gap_start],
            coinbase[available_columns(coinbase, list(frame.columns))],
        ],
        ignore_index=True,
    )
    combined = combined.drop_duplicates("date", keep="last").sort_values("date")
    combined.attrs["provider"] = "CCXT consensus + Coinbase gap fill"
    combined.attrs["ccxt_status"] = frame.attrs.get("ccxt_status", {})
    combined.attrs["coinbase_gap_fill_status"] = {
        "fallback_used": True,
        "gap_fill_start": gap_start,
        "gap_fill_rows": len(coinbase),
        "price_breakdown": coinbase_gap_fill_breakdown(coinbase, frame, gap_start),
        "warning": (
            f"CCXT consensus had a daily history gap; Coinbase replaced prices from "
            f"{gap_start} onward."
        ),
    }
    LOGGER.warning(
        "Filled %s price history from %s onward with Coinbase because CCXT had a daily gap.",
        coinbase_product_id,
        gap_start,
    )
    return combined


def coinbase_gap_fill_breakdown(
    coinbase: pd.DataFrame,
    ccxt_frame: pd.DataFrame,
    gap_start: str,
) -> dict[str, Any]:
    latest_coinbase = coinbase.sort_values("date").iloc[-1]
    ccxt_before_gap = ccxt_frame[ccxt_frame["date"] < gap_start]
    latest_ccxt = (
        ccxt_before_gap.sort_values("date").iloc[-1]
        if not ccxt_before_gap.empty
        else ccxt_frame.sort_values("date").iloc[-1]
    )
    reference_prices: list[dict[str, Any]] = []
    ccxt_breakdown = ccxt_frame.attrs.get("price_breakdown", {})
    if isinstance(ccxt_breakdown, dict):
        for price in ccxt_breakdown.get("exchange_prices", []):
            if price.get("exchange") == "coinbase":
                continue
            status = price.get("status") or "succesvol geladen"
            if price.get("close") is not None:
                status = "succesvol geladen; niet gebruikt voor eindprijs door CCXT-historiegat"
            reference_prices.append({**price, "used": False, "status": status})
    return {
        "asset": str(latest_coinbase.get("asset", "")).upper(),
        "date": str(latest_coinbase["date"]),
        "method": "Coinbase herstelbron",
        "used_close": round(float(latest_coinbase["close"]), 8),
        "source_count": 1 + len(reference_prices),
        "outlier_count": 0,
        "gap_fill_start": gap_start,
        "ccxt_last_date": str(latest_ccxt["date"]),
        "ccxt_last_close": round(float(latest_ccxt["close"]), 8),
        "exchange_prices": [
            {
                "exchange": "coinbase",
                "symbol": str(latest_coinbase.get("asset", "")) + "-USD",
                "close": round(float(latest_coinbase["close"]), 8),
                "used": True,
                "status": "succesvol gebruikt als herstelbron",
                "deviation_pct": 0.0,
            },
            *reference_prices,
        ],
    }


def first_missing_daily_date(
    frame: pd.DataFrame,
    start: datetime | pd.Timestamp,
    end: datetime | pd.Timestamp,
) -> str | None:
    if frame.empty or "date" not in frame:
        return pd.Timestamp(start).date().isoformat()
    dates = pd.to_datetime(frame["date"], utc=True).dt.date
    available = set(dates.astype(str))
    expected = pd.date_range(
        pd.Timestamp(start).date(),
        pd.Timestamp(end).date() - pd.Timedelta(days=1),
        freq="D",
    ).date.astype(str)
    for date in expected:
        if str(date) not in available:
            return str(date)
    return None


def assert_price_coverage(
    frame: pd.DataFrame,
    start: datetime | pd.Timestamp,
    end: datetime | pd.Timestamp,
    min_coverage_ratio: float,
    min_required_rows: int = 365,
) -> None:
    expected_days = max(1, (pd.Timestamp(end).date() - pd.Timestamp(start).date()).days)
    ratio_rows = int(expected_days * min_coverage_ratio)
    min_rows = min(ratio_rows, min_required_rows)
    if expected_days >= 60:
        min_rows = max(30, min_rows)
    min_rows = max(1, min_rows)
    if len(frame) < min_rows:
        raise ApiError(
            f"CCXT consensus has insufficient history: {len(frame)} rows for "
            f"{expected_days} requested days; minimum usable rows is {min_rows}"
        )
    if len(frame) < ratio_rows:
        LOGGER.warning(
            "CCXT consensus covers %s/%s requested days; continuing because minimum usable "
            "history is %s rows.",
            len(frame),
            expected_days,
            min_rows,
        )


def minimum_price_history_rows(cfg: dict[str, Any]) -> int:
    history_cfg = cfg.get("history", {})
    backtest_cfg = cfg.get("backtest", {})
    warmup = int(history_cfg.get("minimum_warmup_days", 365))
    robust_min = int(history_cfg.get("minimum_robust_observations", 180))
    horizons = [int(value) for value in backtest_cfg.get("horizons_days", [30])]
    max_horizon = max(horizons) if horizons else 30
    return max(warmup, robust_min + 220, 365) + max_horizon


def repair_history_prices(
    df: pd.DataFrame,
    trusted_price_dates: dict[str, set[str]] | None = None,
) -> pd.DataFrame:
    repaired = df.sort_values("date").reset_index(drop=True).copy()
    trusted_price_dates = trusted_price_dates or trusted_dates_from_history(repaired)
    repairs: list[dict[str, Any]] = []
    for column, label in [("sol_close", "SOL-USD history"), ("btc_close", "BTC-USD history")]:
        if column not in repaired:
            continue
        single = repaired[["date", column]].rename(columns={column: "close"})
        fixed = repair_daily_price_outliers(
            single,
            ["close"],
            label,
            trusted_dates=(trusted_price_dates or {}).get(column),
        )
        repaired[column] = fixed["close"]
        repairs.extend(fixed.attrs.get("price_repairs", []))
    if repairs:
        repaired.attrs["price_repairs"] = repairs
    return repaired


def trusted_dates_from_history(df: pd.DataFrame) -> dict[str, set[str]]:
    trusted: dict[str, set[str]] = {}
    for price_column, count_column in [
        ("sol_close", "sol_price_source_count"),
        ("btc_close", "btc_price_source_count"),
    ]:
        if count_column not in df:
            continue
        counts = pd.to_numeric(df[count_column], errors="coerce")
        trusted[price_column] = set(df.loc[counts >= 2, "date"].astype(str))
    return trusted


def last_completed_utc_day_end() -> datetime:
    now = pd.Timestamp(utc_now())
    return datetime(now.year, now.month, now.day, tzinfo=UTC)


def prepare_dataset(mode: str) -> pd.DataFrame:
    cfg = settings()
    ind = indicators()
    history = load_or_fetch_history(mode)
    df = add_features(history)
    df.attrs.update(history.attrs)
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
            current_blocks.get("network_usage"),
            current_blocks.get("capital"),
        )
        regimes.append(reg)
    for block, block_values in block_scores.items():
        scored[f"{block}_score"] = block_values
    signal_scores: list[float | None] = []
    for _, row in scored.iterrows():
        current_blocks = {block: row.get(f"{block}_score") for block in ind["blocks"]}
        signal, _ = weighted_average(current_blocks, ind["validated_market_signal"])
        signal_scores.append(signal)
    scored["market_signal_score"] = signal_scores
    scored["regime"] = regimes
    scored.attrs.update(df.attrs)
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
    horizons = cfg["backtest"]["horizons_days"]
    backtest = run_backtest(df, ind["analog_features"], horizons)
    analogs = find_analogs(
        df, last_index, ind["analog_features"], cfg["project"]["default_horizon_days"]
    )
    analog_stats = analog_summary(analogs, cfg["project"]["default_horizon_days"])
    price_repairs = df.attrs.get("price_repairs", [])
    price_source_status = df.attrs.get("price_source_status", {})
    source_status = build_source_status(
        mode,
        generated=iso_z(now),
        latest=latest,
        price_repairs=price_repairs,
        price_source_status=price_source_status,
    )
    breadth_score, breadth_summary, breadth_drivers = score_ecosystem_breadth(
        source_status["ecosystem_breadth"]
    )
    rpc_score, rpc_metrics, rpc_summary = score_network_context(
        source_status["sources"]["solana_rpc"].get("context")
    )
    base_network_usage = rounded_or_none(latest.get("network_usage_score"))
    network_usage, _ = weighted_average(
        {"validated_network": base_network_usage, "rpc_context": rpc_score},
        {"validated_network": 0.85, "rpc_context": 0.15},
    )
    blocks: dict[str, float | None] = {
        "price_strength": rounded_or_none(latest.get("price_strength_score")),
        "network_usage": network_usage,
        "capital": rounded_or_none(latest.get("capital_score")),
        "ecosystem_breadth": breadth_score,
    }
    market_signal, missing_blocks = weighted_average(blocks, ind["validated_market_signal"])
    reg, reg_text = regime(blocks["price_strength"], blocks["network_usage"], blocks["capital"])
    data_quality = source_status["data_quality_score"]
    quality = evidence_quality(
        data_quality,
        analog_stats,
        backtest.summary,
        stability=70.0,
        missing_sources=source_status["missing_validated_sources"],
        critical_error=source_status["critical_error"],
    )
    if breadth_score is not None:
        quality["caps"].append("Breedte in ecosysteem telt beperkt mee en is nog experimenteel.")
    if rpc_score is not None:
        quality["caps"].append("RPC-netwerkcontext telt alleen actueel mee, niet in de backtest.")
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
    interpretation = interpret_market(reg, blocks, market_signal, quality["score"], analog_stats)
    historical_context = build_historical_context(analog_stats, language_label)
    data_audit = build_data_audit(
        df=df,
        source_status=source_status,
        generated=generated,
        cutoff=cutoff,
        analog_count=analog_stats.get("count"),
        breadth=source_status["ecosystem_breadth"],
        rpc_metrics=rpc_metrics,
    )
    details = block_details(
        blocks,
        ind["validated_market_signal"],
        base_network_usage,
        rpc_score,
        rpc_metrics,
        rpc_summary,
        breadth_summary,
        breadth_drivers,
        latest,
    )
    indicator_tabs = build_indicator_tabs(
        df=df,
        latest=latest,
        details=details,
        blocks=blocks,
        source_audit=data_audit,
        breadth=source_status["ecosystem_breadth"],
        base_network_usage=base_network_usage,
        rpc_score=rpc_score,
        rpc_metrics=rpc_metrics,
    )
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
            "regime_title": interpretation["title"],
            "regime_text": reg_text,
            "market_signal_label": score_label(market_signal),
            "evidence_label": quality["label"],
            "language_label": language_label,
            "conclusion": interpretation["body"],
            "interpretation_note": interpretation["note"],
            "what_would_change": what_would_change(blocks),
        },
        "scores": {
            "market_signal": market_signal,
            "evidence_quality": quality["score"],
            "blocks": {k: rounded_or_none(v) for k, v in blocks.items()},
            "block_weights": ind["validated_market_signal"],
            "block_details": details,
            "missing_blocks": missing_blocks,
            "evidence_components": quality["components"],
            "quality_caps": quality["caps"],
            "method_note": (
                "De eindscore is een gewogen indicatorscore van 0 tot 100. Het is geen "
                "kanspercentage en geen beleggingsadvies."
            ),
        },
        "current": {
            "sol_price": round(float(latest["sol_close"]), 2),
            "btc_price": round(float(latest["btc_close"]), 2),
            "live_sol_price": current_price_or_none(source_status, "solana"),
            "live_btc_price": current_price_or_none(source_status, "bitcoin"),
            "risk": {
                "volatility_30d": round(float(latest["realized_volatility_30d"]), 4),
                "drawdown_90d": round(float(latest["drawdown_90d"]), 4),
                "price_source_difference_pct": source_status["price_difference_pct"],
                "warnings": source_status["warnings"],
            },
            "ecosystem_breadth": source_status["ecosystem_breadth"],
            "ecosystem_breadth_score": breadth_score,
            "network_context": source_status["sources"]["solana_rpc"].get("context"),
            "network_context_metrics": rpc_metrics,
            "network_context_score": rpc_score,
        },
        "analog_summary": analog_stats,
        "historical_context": historical_context,
        "data_audit": data_audit,
        "indicator_tabs": indicator_tabs,
        "source_status": source_status["sources"],
    }
    llm_interpretation = build_interpretation(
        dashboard, backtest.summary, generated, cfg.get("llm_interpretation", {})
    )
    dashboard["llm_interpretation"] = {
        "status": llm_interpretation["status"],
        "provider": llm_interpretation["provider"],
        "model": llm_interpretation["model"],
        "llm_called_at_utc": llm_interpretation["llm_called_at_utc"],
    }
    write_signal_research(dashboard, latest, generated, cutoff, mode)
    maybe_append_prediction(dashboard, latest)
    write_all_json(
        dashboard=dashboard,
        df=df,
        analogs=analogs,
        backtest=backtest.summary,
        source_status=source_status,
        interpretation=llm_interpretation,
        generated=generated,
        cutoff=cutoff,
    )
    return dashboard


def build_source_status(
    mode: str,
    generated: str,
    latest: pd.Series,
    price_repairs: list[dict[str, Any]] | None = None,
    price_source_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    breadth_notice = (
        "Experimentele indicator — nog onvoldoende historische waarnemingen voor een "
        "betrouwbare backtest."
    )
    ccxt_available = bool(price_source_status) and not any(
        row.get("fallback_used") for row in (price_source_status or {}).values()
    )
    status: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at_utc": generated,
        "sources": {
            "coinbase": {
                "available": True,
                "role": "fallback historical prices",
                "validated_signal_source": True,
            },
            "ccxt_price_consensus": {
                "available": ccxt_available,
                "role": "multi-exchange historical price consensus",
                "validated_signal_source": True,
                "context": price_source_status or {},
            },
            "coingecko": {
                "available": False,
                "role": "current cross-check and ecosystem breadth",
                "validated_signal_source": False,
            },
            "defillama": {
                "available": mode == "production",
                "role": "historical DeFi data",
                "validated_signal_source": True,
            },
            "solana_rpc": {
                "available": False,
                "role": "current network context",
                "validated_signal_source": False,
            },
        },
        "warnings": [],
        "price_difference_pct": None,
        "price_repairs": price_repairs or [],
        "price_source_status": price_source_status or {},
        "ecosystem_breadth": {
            "available": False,
            "historically_validated": False,
            "notice": breadth_notice,
        },
        "missing_validated_sources": 0,
        "critical_error": False,
        "data_quality_score": 82.0 if mode == "demo" else 100.0,
    }
    if mode == "demo":
        status["sources"]["coinbase"]["available"] = False
        status["sources"]["coinbase"]["note"] = "Demomodus gebruikt synthetische testdata."
        status["sources"]["defillama"]["available"] = False
        status["sources"]["defillama"]["note"] = "Demomodus gebruikt synthetische testdata."
        status["warnings"].append("Demodata — dit zijn geen actuele marktgegevens.")
        return status

    if price_repairs:
        status["warnings"].append(
            f"{len(price_repairs)} verdachte dagprijswaarde(n) gerepareerd met vorige "
            "geldige prijs."
        )
        status["data_quality_score"] -= min(15, 5 * len(price_repairs))

    price_status = price_source_status or {}
    if price_status:
        fallback_used = any(row.get("fallback_used") for row in price_status.values())
        outlier_count = sum(
            int(row.get("outlier_count") or 0)
            for row in price_status.values()
            if isinstance(row, dict)
        )
        if fallback_used:
            status["warnings"].append("CCXT-prijsconsensus viel terug op Coinbase voor een asset.")
            status["data_quality_score"] -= 8
        if outlier_count:
            status["warnings"].append(
                f"{outlier_count} exchange-candle(s) genegeerd buiten de prijsconsensus."
            )

    try:
        current = fetch_coingecko_current()
        status["sources"]["coingecko"]["available"] = True
        status["sources"]["coingecko"]["last_success_at_utc"] = generated
        status["sources"]["coingecko"]["current_prices"] = current
        sol_price = float(current["solana"]["usd"])
        coinbase_price = float(latest["sol_close"])
        diff = abs(sol_price - coinbase_price) / coinbase_price * 100
        status["price_difference_pct"] = round(diff, 2)
        source_cfg = load_yaml("config/sources.yml")
        max_diff = float(source_cfg["cross_source"]["max_price_difference_pct"])
        if diff > max_diff:
            status["warnings"].append(
                "De actuele prijsbronnen wijken meer dan gebruikelijk van elkaar af."
            )
            status["data_quality_score"] -= 12
    except Exception as exc:  # pragma: no cover - network dependent
        status["sources"]["coingecko"]["warning"] = str(exc)
        status["warnings"].append("CoinGecko is niet beschikbaar voor actuele prijscontrole.")
        status["data_quality_score"] -= 10

    try:
        breadth = fetch_coingecko_breadth(CURATED, settings()["breadth"]["number_of_tokens"])
        status["ecosystem_breadth"] = {
            key: value for key, value in breadth.items() if key != "tokens"
        }
        status["ecosystem_breadth"]["available"] = True
        status["ecosystem_breadth"]["last_success_at_utc"] = generated
        append_unique(
            CURATED / "breadth_snapshots.jsonl",
            {"snapshot_at_utc": generated, **breadth},
            ["snapshot_at_utc"],
        )
    except Exception as exc:  # pragma: no cover - network dependent
        status["ecosystem_breadth"]["warning"] = str(exc)

    for column, source_name in [
        ("tvl", "defillama"),
        ("stablecoins", "defillama"),
        ("dex_volume", "defillama"),
        ("fees", "defillama"),
    ]:
        if column not in latest or pd.isna(latest[column]):
            status["warnings"].append(f"Ontbrekende gevalideerde bronwaarde: {column}.")
            status["data_quality_score"] -= 8
            status["sources"][source_name]["available"] = False

    if not status["sources"]["defillama"]["available"]:
        status["missing_validated_sources"] += 1
    if not status["sources"]["coinbase"]["available"]:
        status["missing_validated_sources"] += 1

    try:
        status["sources"]["solana_rpc"]["context"] = fetch_rpc_context()
        status["sources"]["solana_rpc"]["available"] = True
        status["sources"]["solana_rpc"]["last_success_at_utc"] = generated
    except Exception as exc:  # pragma: no cover - network dependent
        status["sources"]["solana_rpc"]["warning"] = str(exc)

    status["data_quality_score"] = max(0.0, round(status["data_quality_score"], 2))
    return status


def score_ecosystem_breadth(
    breadth: dict[str, Any],
) -> tuple[float | None, str, list[str]]:
    if not breadth.get("available"):
        return None, "Niet beschikbaar bij deze update.", ["CoinGecko-breedtedata ontbreekt."]
    positive_7d = breadth.get("positive_7d_share")
    positive_24h = breadth.get("positive_24h_share")
    median_7d = breadth.get("median_return_7d")
    concentration = breadth.get("top3_market_cap_share")
    values = {
        "positive_7d": share_to_score(positive_7d),
        "positive_24h": share_to_score(positive_24h),
        "median_7d": return_to_score(median_7d),
        "cap_spread": concentration_to_score(concentration),
    }
    score, _ = weighted_average(
        values,
        {"positive_7d": 0.40, "positive_24h": 0.20, "median_7d": 0.30, "cap_spread": 0.10},
    )
    token_count = breadth.get("token_count", 0)
    summary = (
        f"{pct_text(positive_7d)} van de gevolgde Solana-tokens staat 7 dagen positief; "
        f"mediaan rendement {pct_text(median_7d)}."
    )
    drivers = [
        f"Steekproef: {token_count} grootste bruikbare Solana-ecosysteemtokens.",
        f"24u positief: {pct_text(positive_24h)}.",
        f"Top-3 concentratie: {pct_text(concentration)} van de gemeten market cap.",
    ]
    return score, summary, drivers


def score_network_context(
    context: dict[str, Any] | None,
) -> tuple[float | None, dict[str, Any], str]:
    if not context:
        return None, {}, "RPC-context ontbreekt bij deze update."
    samples = context.get("recent_performance_samples") or []
    seconds = sum(float(row.get("samplePeriodSecs") or 0) for row in samples)
    non_vote = sum(float(row.get("numNonVoteTransactions") or 0) for row in samples)
    total = sum(float(row.get("numTransactions") or 0) for row in samples)
    if seconds <= 0 or non_vote <= 0:
        return None, {}, "RPC-performance samples bevatten onvoldoende transactiedata."
    non_vote_tps = non_vote / seconds
    total_tps = total / seconds if total else None
    score = clamp_score(35 + ((non_vote_tps - 500) / 2000) * 55)
    metrics = {
        "non_vote_tps": round(non_vote_tps, 1),
        "total_tps": round(total_tps, 1) if total_tps is not None else None,
        "sample_count": len(samples),
        "transaction_count": context.get("transaction_count"),
        "historically_validated": False,
    }
    summary = (
        f"Actuele RPC-steekproef: circa {metrics['non_vote_tps']} niet-stemtransacties per "
        "seconde. Deze context is nuttig, maar nog niet historisch gebacktest."
    )
    return score, metrics, summary


def block_details(
    blocks: dict[str, float | None],
    weights: dict[str, float],
    base_network_usage: float | None,
    rpc_score: float | None,
    rpc_metrics: dict[str, Any],
    rpc_summary: str,
    breadth_summary: str,
    breadth_drivers: list[str],
    latest: pd.Series,
) -> list[dict[str, Any]]:
    return [
        {
            "key": "price_strength",
            "title": "Koerskracht",
            "weight": weights["price_strength"],
            "score": blocks.get("price_strength"),
            "score_label": score_band(blocks.get("price_strength")),
            "score_note": score_note(blocks.get("price_strength")),
            "status": "Historisch gevalideerd",
            "summary": block_summary("price_strength", blocks.get("price_strength")),
            "drivers": [
                f"SOL 7d: {pct_text(latest.get('sol_return_7d'))}.",
                f"SOL 30d: {pct_text(latest.get('sol_return_30d'))}.",
                f"Relatieve sterkte vs BTC 7d: {pct_text(latest.get('relative_strength_btc_7d'))}.",
                f"Afstand tot 50-daagse trend: {pct_text(latest.get('price_vs_sma50'))}.",
            ],
            "metrics": [
                metric("SOL 7d", pct_text(latest.get("sol_return_7d"))),
                metric("SOL 30d", pct_text(latest.get("sol_return_30d"))),
                metric("vs BTC 7d", pct_text(latest.get("relative_strength_btc_7d"))),
            ],
        },
        {
            "key": "network_usage",
            "title": "Gebruik",
            "weight": weights["network_usage"],
            "score": blocks.get("network_usage"),
            "score_label": score_band(blocks.get("network_usage")),
            "score_note": score_note(blocks.get("network_usage")),
            "status": "Grotendeels gevalideerd",
            "summary": block_summary("network_usage", blocks.get("network_usage")),
            "drivers": [
                f"DEX-volume 7d/30d: {ratio_text(latest.get('dex_volume_ratio_7d_30d'))}.",
                f"Fees 7d/30d: {ratio_text(latest.get('fees_ratio_7d_30d'))}.",
                f"Gevalideerde DeFi/fee-score: {score_text(base_network_usage)}.",
                f"Actuele RPC-score: {score_text(rpc_score)}.",
                rpc_summary,
            ],
            "metrics": [
                metric("DEX 7d/30d", ratio_text(latest.get("dex_volume_ratio_7d_30d"))),
                metric("Fees 7d/30d", ratio_text(latest.get("fees_ratio_7d_30d"))),
                metric("Niet-stem TPS", number_text(rpc_metrics.get("non_vote_tps"))),
            ],
        },
        {
            "key": "capital",
            "title": "Kapitaalstromen",
            "weight": weights["capital"],
            "score": blocks.get("capital"),
            "score_label": score_band(blocks.get("capital")),
            "score_note": score_note(blocks.get("capital")),
            "status": "Historisch gevalideerd",
            "summary": block_summary("capital", blocks.get("capital")),
            "drivers": [
                f"Stablecoinvoorraad 30d: {pct_text(latest.get('stablecoin_change_30d'))}.",
                f"TVL 30d: {pct_text(latest.get('tvl_change_30d'))}.",
                capital_scale_note(blocks.get("capital")),
            ],
            "metrics": [
                metric("Stablecoins 30d", pct_text(latest.get("stablecoin_change_30d"))),
                metric("TVL 30d", pct_text(latest.get("tvl_change_30d"))),
                metric("Schaal", "max" if is_capped(blocks.get("capital")) else "relatief"),
            ],
        },
        {
            "key": "ecosystem_breadth",
            "title": "Breedte in ecosysteem",
            "weight": weights["ecosystem_breadth"],
            "score": blocks.get("ecosystem_breadth"),
            "score_label": score_band(blocks.get("ecosystem_breadth")),
            "score_note": score_note(blocks.get("ecosystem_breadth")),
            "status": "Experimenteel, beperkt meegewogen",
            "summary": breadth_summary,
            "drivers": breadth_drivers,
            "metrics": [],
        },
    ]


def build_indicator_tabs(
    df: pd.DataFrame,
    latest: pd.Series,
    details: list[dict[str, Any]],
    blocks: dict[str, float | None],
    source_audit: dict[str, Any],
    breadth: dict[str, Any],
    base_network_usage: float | None,
    rpc_score: float | None,
    rpc_metrics: dict[str, Any],
) -> dict[str, Any]:
    detail_by_key = {item["key"]: item for item in details}
    price = detail_by_key["price_strength"]
    network = detail_by_key["network_usage"]
    capital = detail_by_key["capital"]
    ecosystem = detail_by_key["ecosystem_breadth"]
    network_tab_score, _ = weighted_average(
        {
            "network_usage": blocks.get("network_usage"),
            "ecosystem_breadth": blocks.get("ecosystem_breadth"),
        },
        {
            "network_usage": network["weight"],
            "ecosystem_breadth": ecosystem["weight"],
        },
    )
    return {
        "price": {
            "title": "Prijs",
            "subtitle": "Koerskracht van SOL, inclusief relatieve sterkte tegenover BTC.",
            "score": price["score"],
            "weight": price["weight"],
            "status": price["status"],
            "summary": price["summary"],
            "note": price["score_note"],
            "components": [
                component(
                    "SOL 7 dagen",
                    pct_text(latest.get("sol_return_7d")),
                    latest.get("sol_return_7d__score"),
                    "20% binnen prijsblok",
                    "Kortetermijnmomentum van SOL zelf.",
                ),
                component(
                    "SOL 30 dagen",
                    pct_text(latest.get("sol_return_30d")),
                    latest.get("sol_return_30d__score"),
                    "15% binnen prijsblok",
                    "Middellange koersbeweging van SOL.",
                ),
                component(
                    "Relatief vs BTC 7d",
                    pct_text(latest.get("relative_strength_btc_7d")),
                    latest.get("relative_strength_btc_7d__score"),
                    "30% binnen prijsblok",
                    "Meet of SOL beter of slechter beweegt dan BTC.",
                ),
                component(
                    "Afstand tot 50d trend",
                    pct_text(latest.get("price_vs_sma50")),
                    latest.get("price_vs_sma50__score"),
                    "20% binnen prijsblok",
                    "Laat zien of de koers boven of onder de eigen trend ligt.",
                ),
            ],
            "sources": source_rows_by_name(
                source_audit, ["CCXT consensus", "Coinbase fallback", "CoinGecko"]
            ),
            "trend": {
                "rows": trend_rows(
                    df,
                    {
                        "SOL slotkoers": "sol_close",
                        "Koerskracht": "price_strength_score",
                        "Relatief vs BTC 7d": "relative_strength_btc_7d",
                    },
                ),
                "series": [
                    {"key": "SOL slotkoers", "label": "SOL slotkoers", "unit": "$"},
                    {"key": "Koerskracht", "label": "Koerskracht", "unit": "/100"},
                    {"key": "Relatief vs BTC 7d", "label": "Relatief vs BTC 7d", "unit": "%"},
                ],
            },
        },
        "network": {
            "title": "Gebruik & ecosysteem",
            "subtitle": "Gebruik van DeFi-activiteit, fees, actuele RPC-context en breedte.",
            "score": network_tab_score,
            "weight": network["weight"] + ecosystem["weight"],
            "status": "Grotendeels gevalideerd; breedte in ecosysteem is experimenteel",
            "summary": (
                f"{network['summary']} Breedte in ecosysteem: {ecosystem['summary']}"
            ),
            "note": (
                "Gebruik telt volledig mee binnen de historische toets; RPC-context en "
                "breedte in ecosysteem zijn actueel en transparant beperkt meegewogen."
            ),
            "components": [
                component(
                    "DEX-volume 7d/30d",
                    ratio_text(latest.get("dex_volume_ratio_7d_30d")),
                    latest.get("dex_volume_ratio_7d_30d__score"),
                    "60% binnen gebruik",
                    "Vergelijkt recente DEX-activiteit met het 30-daags gemiddelde.",
                ),
                component(
                    "Fees 7d/30d",
                    ratio_text(latest.get("fees_ratio_7d_30d")),
                    latest.get("fees_ratio_7d_30d__score"),
                    "40% binnen gebruik",
                    "Meet of betaalde fees boven of onder normaal liggen.",
                ),
                component(
                    "RPC-context",
                    f"{score_text(rpc_score)}; {number_text(rpc_metrics.get('non_vote_tps'))} TPS",
                    rpc_score,
                    "15% correctie op gebruik",
                    "Actuele steekproef uit Solana RPC-performance samples.",
                ),
                component(
                    "Breedte in ecosysteem",
                    breadth_value_text(breadth),
                    blocks.get("ecosystem_breadth"),
                    "10% van eindscore",
                    "Meet of meerdere Solana-ecosysteemtokens tegelijk meedoen.",
                ),
                component(
                    "Gevalideerde basis",
                    score_text(base_network_usage),
                    base_network_usage,
                    "85% van gebruik",
                    "Alleen DeFi/fee-data die historisch is meegetest.",
                ),
            ],
            "sources": source_rows_by_name(source_audit, ["DeFiLlama", "Solana RPC", "CoinGecko"]),
            "trend": {
                "rows": trend_rows(
                    df,
                    {
                        "Gebruik": "network_usage_score",
                        "DEX 7d/30d": "dex_volume_ratio_7d_30d",
                        "Fees 7d/30d": "fees_ratio_7d_30d",
                    },
                ),
                "series": [
                    {"key": "Gebruik", "label": "Gebruik", "unit": "/100"},
                    {"key": "DEX 7d/30d", "label": "DEX 7d/30d", "unit": "x"},
                    {"key": "Fees 7d/30d", "label": "Fees 7d/30d", "unit": "x"},
                ],
            },
        },
        "capital": {
            "title": "Kapitaalstromen",
            "subtitle": "Kapitaalstromen via stablecoinvoorraad en TVL op Solana.",
            "score": capital["score"],
            "weight": capital["weight"],
            "status": capital["status"],
            "summary": capital["summary"],
            "note": capital["score_note"],
            "components": [
                component(
                    "Stablecoins 30d",
                    pct_text(latest.get("stablecoin_change_30d")),
                    latest.get("stablecoin_change_30d__score"),
                    "55% binnen kapitaalblok",
                    "Groei of krimp van stablecoinvoorraad op Solana.",
                ),
                component(
                    "TVL 30d",
                    pct_text(latest.get("tvl_change_30d")),
                    latest.get("tvl_change_30d__score"),
                    "45% binnen kapitaalblok",
                    "Groei of krimp van total value locked.",
                ),
                component(
                    "Schaalduiding",
                    "Afgekapt op 100" if is_capped(blocks.get("capital")) else "Relatief",
                    blocks.get("capital"),
                    "Uitleg",
                    capital_scale_note(blocks.get("capital")),
                ),
            ],
            "sources": source_rows_by_name(source_audit, ["DeFiLlama"]),
            "trend": {
                "rows": trend_rows(
                    df,
                    {
                        "Kapitaalstromen": "capital_score",
                        "Stablecoins 30d": "stablecoin_change_30d",
                        "TVL 30d": "tvl_change_30d",
                    },
                ),
                "series": [
                    {"key": "Kapitaalstromen", "label": "Kapitaalstromen", "unit": "/100"},
                    {"key": "Stablecoins 30d", "label": "Stablecoins 30d", "unit": "%"},
                    {"key": "TVL 30d", "label": "TVL 30d", "unit": "%"},
                ],
            },
        },
    }


def component(
    label: str,
    value: str,
    score: float | None,
    weight: str,
    description: str,
) -> dict[str, str | float | None]:
    return {
        "label": label,
        "value": value,
        "score": rounded_or_none(score),
        "weight": weight,
        "description": description,
    }


def source_rows_by_name(source_audit: dict[str, Any], names: list[str]) -> list[dict[str, str]]:
    rows = source_audit.get("sources", [])
    by_name = {row.get("name"): row for row in rows}
    return [by_name[name] for name in names if name in by_name]


def trend_rows(
    df: pd.DataFrame,
    fields: dict[str, str],
    days: int = 120,
) -> list[dict[str, str | float | None]]:
    selected = df.tail(days)
    rows: list[dict[str, str | float | None]] = []
    for _, row in selected.iterrows():
        item: dict[str, str | float | None] = {"date": str(row.get("date"))}
        for label, column in fields.items():
            item[label] = rounded_or_none(row.get(column)) if column in row else None
        rows.append(item)
    return rows


def breadth_value_text(breadth: dict[str, Any]) -> str:
    if not breadth.get("available"):
        return "n.v.t."
    return (
        f"{pct_text(breadth.get('positive_7d_share'))} positief 7d; "
        f"{breadth.get('token_count', 0)} tokens"
    )


def current_price_or_none(source_status: dict[str, Any], asset: str) -> float | None:
    value = (
        source_status.get("sources", {})
        .get("coingecko", {})
        .get("current_prices", {})
        .get(asset, {})
        .get("usd")
    )
    return round(float(value), 2) if value is not None else None


def share_to_score(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return clamp_score(float(value) * 100)


def return_to_score(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return clamp_score(50 + float(value) * 500)


def concentration_to_score(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return clamp_score((1 - float(value)) * 100)


def clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 2)


def pct_text(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n.v.t."
    return f"{float(value) * 100:.1f}%"


def score_text(value: float | None) -> str:
    return "n.v.t." if value is None or pd.isna(value) else f"{float(value):.0f}/100"


def score_band(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "niet berekend"
    score = float(value)
    if score >= 99.5:
        return "extreem sterk, afgekapt"
    if score >= 85:
        return "zeer sterk"
    if score >= 66:
        return "sterk"
    if score >= 56:
        return "positief"
    if score >= 45:
        return "neutraal"
    if score >= 35:
        return "zwak"
    return "zeer zwak"


def score_note(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "Geen bruikbare score bij deze update."
    if is_capped(value):
        return "Afgekapt op 100: extreem op historische schaal, geen zekerheid."
    return "Score is relatief ten opzichte van de eigen historie."


def is_capped(value: float | None) -> bool:
    return value is not None and not pd.isna(value) and float(value) >= 99.5


def block_summary(key: str, value: float | None) -> str:
    if value is None or pd.isna(value):
        return "Niet beschikbaar bij deze update."
    score = float(value)
    if key == "price_strength":
        if score >= 66:
            return "SOL toont duidelijke koerskracht, ook relatief tegen de markt."
        if score >= 45:
            return "Koerskracht is gemengd: nog geen overtuigende koersbevestiging."
        return "SOL blijft qua koers achter; prijs bevestigt de onderliggende data nog niet."
    if key == "network_usage":
        if score >= 66:
            return "Gebruik op en rond Solana ligt ruim boven normaal."
        if score >= 45:
            return "Gebruik is rond normaal tot licht positief."
        return "Gebruik geeft nog weinig bevestiging."
    if key == "capital":
        if is_capped(value):
            return "Kapitaalstromen staan extreem hoog op de historische schaal."
        if score >= 66:
            return "Kapitaalstromen naar Solana zijn sterk."
        if score >= 45:
            return "Kapitaalstromen zijn neutraal tot gemengd."
        return "Kapitaalstromen zijn zwak ten opzichte van de eigen historie."
    return "Score op basis van beschikbare indicatoren."


def capital_scale_note(value: float | None) -> str:
    if is_capped(value):
        return "Een score van 100 betekent: afgekapt op het maximum, niet 100% zekerheid."
    return "Score is een relatieve positie op de historische schaal."


def metric(label: str, value: str) -> dict[str, str]:
    return {"label": label, "value": value}


def ratio_text(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n.v.t."
    return f"{float(value):.2f}x"


def number_text(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n.v.t."
    return f"{float(value):,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")


def build_historical_context(analog_stats: dict[str, Any], language_label: str) -> dict[str, Any]:
    positive = analog_stats.get("positive_frequency")
    median = analog_stats.get("median_return")
    p10 = analog_stats.get("p10")
    p90 = analog_stats.get("p90")
    horizon = analog_stats.get("horizon_days")
    count = analog_stats.get("count")
    return {
        "title": "Historische vergelijkingen",
        "summary": (
            f"{language_label}: {pct_text(positive)} positief na {horizon} dagen. "
            f"Mediaan {pct_text(median)}; midden 80% liep van {pct_text(p10)} tot {pct_text(p90)}."
        ),
        "stats": [
            metric("Vergelijkbare dagen", str(count)),
            metric("Positief", pct_text(positive)),
            metric("Mediaan", pct_text(median)),
            metric("Midden 80%", f"{pct_text(p10)} tot {pct_text(p90)}"),
        ],
    }


def build_data_audit(
    df: pd.DataFrame,
    source_status: dict[str, Any],
    generated: str,
    cutoff: str,
    analog_count: int | None,
    breadth: dict[str, Any],
    rpc_metrics: dict[str, Any],
) -> dict[str, Any]:
    first_date = str(df["date"].min()) if "date" in df and not df.empty else "n.v.t."
    last_date = str(df["date"].max()) if "date" in df and not df.empty else "n.v.t."
    rows = len(df)
    warnings = source_status.get("warnings") or []
    price_repairs = source_status.get("price_repairs") or []
    sources = source_status.get("sources", {})
    price_consensus = sources.get("ccxt_price_consensus", {}).get("context", {})
    return {
        "title": "Datakwaliteit & bronnen",
        "summary": (
            f"{rows} historische records van {first_date} t/m {last_date}. "
            f"Laatste dagdata-cutoff: {cutoff}. Update-run: {generated}."
        ),
        "freshness": [
            metric("Update-run", generated),
            metric("Data t/m", cutoff),
            metric("Historie", f"{first_date} t/m {last_date}"),
            metric("Records", str(rows)),
            metric("Prijsreparaties", str(len(price_repairs))),
            metric("Prijsconsensus", price_consensus_summary(price_consensus)),
            metric("Analoge dagen", str(analog_count or 0)),
            metric("Ecosysteem tokens", str(breadth.get("token_count", "n.v.t."))),
            metric("RPC samples", str(rpc_metrics.get("sample_count", "n.v.t."))),
        ],
        "sources": [
            source_row(
                "CCXT consensus",
                sources.get("ccxt_price_consensus", {}),
                "Multi-exchange SOL/BTC dagprijs",
                "Historisch gevalideerd",
                price_consensus_coverage(price_consensus),
            ),
            source_row(
                "Coinbase fallback",
                sources.get("coinbase", {}),
                "Fallback SOL/BTC dagprijzen",
                "Historisch gevalideerd",
                f"{rows} dagrecords",
            ),
            source_row(
                "DeFiLlama",
                sources.get("defillama", {}),
                "TVL, stablecoins, DEX-volume en fees",
                "Historisch gevalideerd",
                (
                    f"{count_present_rows(df, ['tvl', 'stablecoins', 'dex_volume', 'fees'])} "
                    "bruikbare rijen"
                ),
            ),
            source_row(
                "CoinGecko",
                sources.get("coingecko", {}),
                "Liveprijs en breedte in ecosysteem",
                "Actueel/contextueel",
                f"{breadth.get('token_count', 0)} ecosysteemtokens",
            ),
            source_row(
                "Solana RPC",
                sources.get("solana_rpc", {}),
                "Actuele netwerkcontext",
                "Actueel, niet gebacktest",
                f"{rpc_metrics.get('sample_count', 0)} performance samples",
            ),
        ],
        "warnings": warnings,
    }


def source_row(
    name: str,
    source: dict[str, Any],
    role: str,
    validation: str,
    coverage: str,
) -> dict[str, Any]:
    ok = bool(source.get("available"))
    context = source.get("context") or {}
    fallback_used = any(
        isinstance(row, dict) and row.get("fallback_used")
        for row in context.values()
    )
    gap_fill_used = any(
        isinstance(row, dict) and row.get("provider") == "CCXT consensus + Coinbase gap fill"
        for row in context.values()
    )
    status = "Succesvol" if ok else "Niet beschikbaar"
    if gap_fill_used:
        status = "Coinbase herstelbron"
    elif fallback_used:
        status = "Fallback gebruikt"
    last_success = source.get("last_success_at_utc")
    if not last_success:
        if ok:
            last_success = "Dataset aanwezig"
        elif gap_fill_used:
            last_success = "Echte Coinbase-data gebruikt"
        elif fallback_used:
            last_success = "Coinbase fallback actief"
        else:
            last_success = "n.v.t."
    warning = source.get("warning") or source.get("note") or ""
    if gap_fill_used and not warning:
        warning = (
            "Geen fake data: CCXT leverde multi-exchange data, maar had een historisch gat. "
            "Vanaf dat gat gebruikt het dashboard echte Coinbase-dagprijzen."
        )
    elif fallback_used and not warning:
        warning = "Multi-exchange consensus niet volledig beschikbaar; fallback is gebruikt."
    return {
        "name": name,
        "status": status,
        "role": role,
        "validation": validation,
        "coverage": coverage,
        "last_success_at_utc": str(last_success),
        "warning": str(warning),
        "price_breakdown": price_source_breakdown(context),
    }


def price_source_breakdown(price_status: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for asset, row in sorted(price_status.items()):
        if not isinstance(row, dict):
            continue
        breakdown = row.get("price_breakdown")
        if not isinstance(breakdown, dict):
            continue
        rows.append(
            {
                "asset": str(asset).upper(),
                "provider": row.get("provider", breakdown.get("method", "prijsbron")),
                "date": breakdown.get("date"),
                "method": breakdown.get("method"),
                "used_close": breakdown.get("used_close"),
                "source_count": breakdown.get("source_count"),
                "outlier_count": breakdown.get("outlier_count"),
                "max_deviation_pct": breakdown.get("max_deviation_pct"),
                "gap_fill_start": breakdown.get("gap_fill_start"),
                "ccxt_last_date": breakdown.get("ccxt_last_date"),
                "ccxt_last_close": breakdown.get("ccxt_last_close"),
                "exchange_prices": breakdown.get("exchange_prices", []),
            }
        )
    return rows


def price_consensus_summary(price_status: dict[str, Any]) -> str:
    if not price_status:
        return "n.v.t."
    parts = []
    for asset, row in price_status.items():
        if not isinstance(row, dict):
            continue
        provider = row.get("provider", "prijsbron")
        rows = row.get("rows", 0)
        min_sources = row.get("min_source_count", "n.v.t.")
        parts.append(f"{str(asset).upper()}: {provider}, {rows} rijen, min {min_sources} bronnen")
    return "; ".join(parts) if parts else "n.v.t."


def price_consensus_coverage(price_status: dict[str, Any]) -> str:
    if not price_status:
        return "Niet beschikbaar"
    total_rows = sum(
        int(row.get("rows") or 0) for row in price_status.values() if isinstance(row, dict)
    )
    outliers = sum(
        int(row.get("outlier_count") or 0)
        for row in price_status.values()
        if isinstance(row, dict)
    )
    return f"{total_rows} consensusrijen; {outliers} genegeerde exchange-candles"


def count_present_rows(df: pd.DataFrame, columns: list[str]) -> int:
    available = [column for column in columns if column in df]
    if not available:
        return 0
    return int(df[available].dropna(how="all").shape[0])


def interpret_market(
    reg: str,
    blocks: dict[str, float | None],
    signal: float | None,
    quality: float,
    analog_stats: dict[str, Any],
) -> dict[str, str]:
    positive_frequency = analog_stats.get("positive_frequency")
    signal_text = score_text(signal)
    evidence_text = score_text(quality)
    if signal is None:
        return {
            "title": "Onvoldoende actuele data",
            "body": "Er is onvoldoende actuele kerninformatie voor een betrouwbare conclusie.",
            "note": "Wacht op een volledige data-update voordat je dit interpreteert.",
        }

    price = blocks.get("price_strength") or 0
    network = blocks.get("network_usage") or 0
    capital = blocks.get("capital") or 0
    history_is_mixed = positive_frequency is not None and positive_frequency < 0.5
    weak_evidence = quality < 60

    if reg == "building_under_surface":
        title = "Onderliggende kracht bouwt op"
        body = (
            "Gebruik en kapitaalstromen zijn sterk, terwijl koerskracht nog "
            "achterblijft. Dat wijst op verbetering onder de oppervlakte, niet op een "
            "volledig bevestigde trend."
        )
    elif reg == "confirmed_trend":
        title = "Trend wordt breed bevestigd"
        body = (
            "Koerskracht, gebruik en kapitaalstromen wijzen dezelfde kant op. Dit is "
            "het meest overtuigende type positief signaal binnen deze methode."
        )
    elif reg == "fragile_rally":
        title = "Prijs loopt vooruit op bevestiging"
        body = (
            "De koers oogt sterk, maar gebruik en kapitaalstromen bevestigen die beweging "
            "nog onvoldoende. Dat maakt het signaal kwetsbaarder."
        )
    elif reg == "risk_regime":
        title = "Zwak marktbeeld"
        body = (
            "Koerskracht en onderliggende bevestiging zijn zwak. De methode vraagt hier "
            "om terughoudendheid."
        )
    else:
        title = "Gemengd marktbeeld"
        body = (
            "De blokken geven geen eenduidige richting. Dit vraagt om terughoudende "
            "interpretatie."
        )

    note_parts = [f"Huidige sterkte {signal_text}; onderbouwing {evidence_text}."]
    if history_is_mixed:
        note_parts.append(
            "Vergelijkbare eerdere dagen zijn gemengd: "
            f"{pct_text(positive_frequency)} was positief."
        )
    if weak_evidence:
        note_parts.append("De onderbouwing is beperkt, dus de conclusie is geen hard signaal.")
    if capital >= 99.5:
        note_parts.append("Kapitaal staat op 100 omdat de score op het maximum is afgekapt.")
    if price < 55 and (network >= 70 or capital >= 70):
        note_parts.append("De kernspanning: onderliggende data is sterker dan de koers.")
    return {"title": title, "body": body, "note": " ".join(note_parts)}



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
    return f"{phrase} De onderbouwing is {quality:.0f}/100."


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
    if (blocks.get("network_usage") or 0) < 55:
        items.append("Gebruik, DEX-volume en fees stijgen boven hun normale niveau.")
    else:
        items.append("Gebruik of DEX-volume zakt terug onder het normale niveau.")
    if (blocks.get("capital") or 0) < 55:
        items.append("Stablecoinvoorraad en TVL beginnen duidelijk toe te nemen.")
    else:
        items.append("TVL-groei of stablecoinvoorraad draait om.")
    if (blocks.get("ecosystem_breadth") or 0) < 55:
        items.append("Meer Solana-ecosysteemtokens gaan tegelijk meedoen aan de beweging.")
    else:
        items.append("De beweging versmalt naar minder Solana-ecosysteemtokens.")
    return items


def signal_research_record(
    dashboard: dict[str, Any],
    latest: pd.Series,
    generated: str,
    cutoff: str,
    mode: str,
) -> dict[str, Any]:
    blocks = dashboard.get("scores", {}).get("blocks", {})
    weights = normalized_signal_weights(dashboard.get("scores", {}).get("block_weights", {}))
    current = dashboard.get("current", {})
    summary = dashboard.get("summary", {})
    price_score = rounded_or_none(blocks.get("price_strength"))
    network_score = rounded_or_none(blocks.get("network_usage"))
    capital_score = rounded_or_none(blocks.get("capital"))
    breadth_score = rounded_or_none(blocks.get("ecosystem_breadth"))
    return {
        "run_at_utc": generated,
        "data_cutoff_utc": cutoff,
        "method_version": dashboard.get("method_version"),
        "mode": mode,
        "sol_price": rounded_or_none(current.get("sol_price")),
        "btc_price": rounded_or_none(current.get("btc_price")),
        "sol_live_price": rounded_or_none(current.get("live_sol_price")),
        "btc_live_price": rounded_or_none(current.get("live_btc_price")),
        "current_strength_score": rounded_or_none(dashboard.get("scores", {}).get("market_signal")),
        "support_score": rounded_or_none(dashboard.get("scores", {}).get("evidence_quality")),
        "price_strength_score": price_score,
        "network_usage_score": network_score,
        "capital_flows_score": capital_score,
        "ecosystem_breadth_score": breadth_score,
        "regime": summary.get("regime"),
        "regime_title": summary.get("regime_title"),
        "sol_return_1d": rounded_or_none(latest.get("sol_return_1d")),
        "sol_return_7d": rounded_or_none(latest.get("sol_return_7d")),
        "sol_return_30d": rounded_or_none(latest.get("sol_return_30d")),
        "btc_return_7d": rounded_or_none(latest.get("btc_return_7d")),
        "btc_return_30d": rounded_or_none(latest.get("btc_return_30d")),
        "relative_strength_btc_7d": rounded_or_none(latest.get("relative_strength_btc_7d")),
        "relative_strength_btc_30d": rounded_or_none(latest.get("relative_strength_btc_30d")),
        "price_vs_sma50": rounded_or_none(latest.get("price_vs_sma50")),
        "price_vs_sma200": rounded_or_none(latest.get("price_vs_sma200")),
        "realized_volatility_30d": rounded_or_none(latest.get("realized_volatility_30d")),
        "drawdown_90d": rounded_or_none(latest.get("drawdown_90d")),
        "dex_volume_ratio_7d_30d": rounded_or_none(latest.get("dex_volume_ratio_7d_30d")),
        "dex_volume_change_30d": rounded_or_none(latest.get("dex_volume_change_30d")),
        "fees_ratio_7d_30d": rounded_or_none(latest.get("fees_ratio_7d_30d")),
        "tvl_change_7d": rounded_or_none(latest.get("tvl_change_7d")),
        "tvl_change_30d": rounded_or_none(latest.get("tvl_change_30d")),
        "stablecoin_change_7d": rounded_or_none(latest.get("stablecoin_change_7d")),
        "stablecoin_change_30d": rounded_or_none(latest.get("stablecoin_change_30d")),
        "price_strength_weight": weights.get("price_strength"),
        "network_usage_weight": weights.get("network_usage"),
        "capital_flows_weight": weights.get("capital_flows"),
        "ecosystem_breadth_weight": weights.get("ecosystem_breadth"),
        "price_strength_contribution": weighted_contribution(
            price_score, weights.get("price_strength")
        ),
        "network_usage_contribution": weighted_contribution(
            network_score, weights.get("network_usage")
        ),
        "capital_flows_contribution": weighted_contribution(
            capital_score, weights.get("capital_flows")
        ),
        "ecosystem_breadth_contribution": weighted_contribution(
            breadth_score, weights.get("ecosystem_breadth")
        ),
    }


def normalized_signal_weights(weights: dict[str, Any]) -> dict[str, float | None]:
    return {
        "price_strength": rounded_or_none(weights.get("price_strength")),
        "network_usage": rounded_or_none(weights.get("network_usage")),
        "capital_flows": rounded_or_none(weights.get("capital") or weights.get("capital_flows")),
        "ecosystem_breadth": rounded_or_none(weights.get("ecosystem_breadth")),
    }


def method_versions_config() -> dict[str, Any]:
    data = load_yaml("config/method_versions.yml")
    versions = data.get("method_versions", {})
    if not isinstance(versions, dict):
        raise ValueError("config/method_versions.yml must contain method_versions mapping")
    for version, meta in versions.items():
        weights = (meta or {}).get("weights", {})
        validate_method_weights(str(version), weights)
    return versions


def validate_method_weights(version: str, weights: dict[str, Any]) -> None:
    required = {key for key, _, _ in DRIVER_ORDER}
    if set(weights) != required:
        missing = sorted(required - set(weights))
        extra = sorted(set(weights) - required)
        raise ValueError(f"Method {version} weight mismatch; missing={missing}, extra={extra}")
    total = 0.0
    for key, value in weights.items():
        if not isinstance(value, int | float) or value < 0:
            raise ValueError(f"Method {version} has invalid weight for {key}: {value}")
        total += float(value)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"Method {version} weights sum to {total}, not 1.0")


def method_weights(method_version: Any) -> dict[str, float]:
    meta = method_versions_config().get(str(method_version), {})
    return {key: float(value) for key, value in (meta.get("weights") or {}).items()}


def method_metadata(method_version: Any) -> dict[str, Any]:
    meta = method_versions_config().get(str(method_version), {})
    if not meta:
        return {
            "label": f"Methode {method_version}",
            "description": "Geen toelichting beschikbaar.",
            "weights": {},
        }
    return meta


def weighted_contribution(score: float | None, weight: float | None) -> float | None:
    if score is None or weight is None:
        return None
    return rounded_or_none(float(score) * float(weight))


def write_signal_research(
    dashboard: dict[str, Any],
    latest: pd.Series,
    generated: str,
    cutoff: str,
    mode: str,
) -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    record = signal_research_record(dashboard, latest, generated, cutoff, mode)
    if mode != "production":
        demo_frame = pd.DataFrame([record])
        write_signal_research_public(
            demo_frame,
            generated=generated,
            cutoff=cutoff,
            method_version=dashboard.get("method_version"),
            persisted=False,
        )
        return

    CURATED.mkdir(parents=True, exist_ok=True)
    new_row = pd.DataFrame([record])
    combined = append_signal_research_atomic(SIGNAL_RESEARCH_PATH, new_row)
    write_signal_research_public(
        combined,
        generated=generated,
        cutoff=cutoff,
        method_version=dashboard.get("method_version"),
        persisted=True,
    )


def read_signal_research_history() -> pd.DataFrame:
    if not SIGNAL_RESEARCH_PATH.exists():
        return pd.DataFrame(columns=SIGNAL_RESEARCH_COLUMNS)
    return pd.read_parquet(SIGNAL_RESEARCH_PATH)


def clean_signal_research_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return production rows for public analysis without mutating source history."""
    if frame.empty:
        return pd.DataFrame(columns=SIGNAL_RESEARCH_COLUMNS)
    cleaned = frame.copy()
    if "mode" not in cleaned:
        cleaned["mode"] = None
    cleaned = cleaned[cleaned["mode"] == "production"]
    cleaned = cleaned.dropna(subset=["run_at_utc"])
    if cleaned["run_at_utc"].duplicated().any():
        raise ApiError("Production signaalonderzoek contains duplicate run_at_utc values")
    return cleaned.sort_values("run_at_utc")


def append_signal_research_atomic(path: Path, new_row: pd.DataFrame) -> pd.DataFrame:
    """Append one production row while preserving all existing Parquet rows and columns."""
    if len(new_row) != 1:
        raise ApiError("Signal research append expects exactly one new row")
    before = parquet_snapshot(path) if path.exists() else None
    existing = pd.DataFrame()
    if path.exists():
        existing = read_existing_signal_research(path)
        if SIGNAL_RESEARCH_KEY not in existing:
            raise ApiError("Existing signal research Parquet misses run_at_utc")
        if existing[SIGNAL_RESEARCH_KEY].duplicated().any():
            raise ApiError("Existing signal research Parquet contains duplicate run_at_utc keys")
    combined, changed = combine_signal_research_rows(existing, new_row)
    if not changed:
        return combined
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        combined.to_parquet(tmp_path, index=False)
        restored = pd.read_parquet(tmp_path)
        validate_signal_research_write(existing, combined, restored, before)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    return pd.read_parquet(path)


def read_existing_signal_research(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        message = f"Cannot read existing signal research Parquet; original left intact: {exc}"
        raise ApiError(message) from exc


def combine_signal_research_rows(
    existing: pd.DataFrame,
    new_row: pd.DataFrame,
) -> tuple[pd.DataFrame, bool]:
    columns = schema_union(existing.columns, SIGNAL_RESEARCH_COLUMNS, new_row.columns)
    normalized_existing = (
        existing.reindex(columns=columns)
        if not existing.empty
        else pd.DataFrame(columns=columns)
    )
    normalized_new = new_row.reindex(columns=columns)
    key = str(normalized_new.iloc[0][SIGNAL_RESEARCH_KEY])
    existing_keys = set(
        normalized_existing.get(SIGNAL_RESEARCH_KEY, pd.Series(dtype="object")).astype(str)
    )
    if key in existing_keys:
        existing_match = normalized_existing[
            normalized_existing[SIGNAL_RESEARCH_KEY].astype(str) == key
        ]
        if len(existing_match) != 1:
            raise ApiError(f"Duplicate signal research key conflict for {key}")
        if stable_records_equal(existing_match.iloc[[0]], normalized_new):
            sorted_existing = normalized_existing.sort_values(SIGNAL_RESEARCH_KEY).reset_index(
                drop=True
            )
            return sorted_existing, False
        raise ApiError(f"Signal research key conflict for {key}: existing row differs")
    combined = (
        normalized_new.copy()
        if normalized_existing.empty
        else pd.concat([normalized_existing, normalized_new], ignore_index=True)
    )
    return combined.sort_values(SIGNAL_RESEARCH_KEY).reset_index(drop=True), True


def schema_union(*column_groups) -> list[str]:
    columns: list[str] = []
    for group in column_groups:
        for column in list(group):
            if column not in columns:
                columns.append(str(column))
    return columns


def validate_signal_research_write(
    existing: pd.DataFrame,
    expected: pd.DataFrame,
    restored: pd.DataFrame,
    before: dict[str, Any] | None,
) -> None:
    if len(restored) != len(expected):
        raise ApiError("Temporary signal research Parquet row count changed after write")
    if list(restored.columns) != list(expected.columns):
        raise ApiError("Temporary signal research Parquet schema changed after write")
    if SIGNAL_RESEARCH_KEY not in restored:
        raise ApiError("Temporary signal research Parquet misses run_at_utc")
    if restored[SIGNAL_RESEARCH_KEY].duplicated().any():
        raise ApiError("Temporary signal research Parquet contains duplicate run keys")
    if before and len(restored) not in {before["row_count"], before["row_count"] + 1}:
        raise ApiError("Unexpected signal research row count after append")
    if not existing.empty:
        restored_old = restored[
            restored[SIGNAL_RESEARCH_KEY].astype(str).isin(existing[SIGNAL_RESEARCH_KEY].astype(str))
        ]
        old_hash = dataframe_content_hash(existing)
        restored_hash = dataframe_content_hash(restored_old.reindex(columns=existing.columns))
        if old_hash != restored_hash:
            raise ApiError("Existing signal research rows changed during append")


def parquet_snapshot(path: Path) -> dict[str, Any]:
    frame = read_existing_signal_research(path)
    key = frame[SIGNAL_RESEARCH_KEY] if SIGNAL_RESEARCH_KEY in frame else pd.Series(dtype="object")
    return {
        "path": str(path),
        "row_count": int(len(frame)),
        "columns": list(frame.columns),
        "dtypes": {column: str(dtype) for column, dtype in frame.dtypes.items()},
        "run_at_min": None if key.empty else str(key.min()),
        "run_at_max": None if key.empty else str(key.max()),
        "run_at_unique": int(key.nunique()) if not key.empty else 0,
        "run_at_duplicates": int(key.duplicated().sum()) if not key.empty else 0,
        "file_sha256": file_sha256(path),
        "content_hash": dataframe_content_hash(frame),
    }


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dataframe_content_hash(frame: pd.DataFrame) -> str:
    if frame.empty:
        payload = {"columns": list(frame.columns), "rows": []}
    else:
        sortable = frame.copy()
        if SIGNAL_RESEARCH_KEY in sortable:
            sortable = sortable.sort_values(SIGNAL_RESEARCH_KEY)
        sortable = sortable.reset_index(drop=True)
        payload = {
            "columns": list(sortable.columns),
            "rows": [
                {column: stable_json_value(row[column]) for column in sortable.columns}
                for _, row in sortable.iterrows()
            ],
        }
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, float):
        return round(value, 12)
    if hasattr(value, "item"):
        try:
            return stable_json_value(value.item())
        except ValueError:
            pass
    return value


def stable_records_equal(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    return dataframe_content_hash(left.reset_index(drop=True)) == dataframe_content_hash(
        right.reset_index(drop=True)
    )


def write_signal_research_public(
    frame: pd.DataFrame,
    generated: str,
    cutoff: str,
    method_version: str | None,
    persisted: bool,
) -> None:
    production_frame = clean_signal_research_frame(frame) if persisted else frame.copy()
    latest_rows = production_frame.tail(50).copy()
    storage_text = "Parquet + JSON" if persisted else "Demo JSON"
    summary = (
        "Elke rij is een productie-run van het dashboard. De volledige dataset staat in "
        "data/curated/signaalonderzoek.parquet en is bedoeld voor later "
        "signaalonderzoek en modelvalidatie."
        if persisted
        else "Demo-weergave voor lokale tests. Deze rijen worden niet opgeslagen in de "
        "onderzoeksdataset en tellen niet mee voor signaalonderzoek."
    )
    write_json(
        SIGNAL_RESEARCH_LATEST_PATH,
        {
            "schema_version": "1.0",
            "generated_at_utc": generated,
            "data_cutoff_utc": cutoff,
            "method_version": method_version,
            "name": "Signaalonderzoek",
            "summary": summary,
            "row_count_total": int(len(frame)),
            "row_count_visible": int(len(latest_rows)),
            "download_path": "./data/signaalonderzoek.parquet" if persisted else None,
            "storage": storage_text,
            "columns": signal_research_columns(),
            "rows": dataframe_json_records(latest_rows),
        },
    )
    if persisted:
        public_path = SITE_DATA / "signaalonderzoek.parquet"
        public_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(SITE_DATA / "signaalonderzoek.parquet", index=False)


def dataframe_json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {column: stable_json_value(row[column]) for column in frame.columns}
        for _, row in frame.iterrows()
    ]


def signal_research_columns() -> list[dict[str, str]]:
    return [
        {
            "key": "run_at_utc",
            "label": "Run",
            "description": "Moment waarop GitHub Actions het dashboard heeft bijgewerkt.",
        },
        {
            "key": "data_cutoff_utc",
            "label": "Data t/m",
            "description": "Laatste marktdag die in de berekening is gebruikt.",
        },
        {
            "key": "sol_price",
            "label": "SOL",
            "description": "SOL-slotkoers uit de gevalideerde dagreeks.",
        },
        {
            "key": "btc_price",
            "label": "BTC",
            "description": "BTC-slotkoers uit de gevalideerde dagreeks.",
        },
        {
            "key": "current_strength_score",
            "label": "Sterkte",
            "description": "Gewogen dashboardscore van 0 tot 100.",
        },
        {
            "key": "support_score",
            "label": "Onderbouwing",
            "description": "Hoe stevig de data en historische toets zijn, van 0 tot 100.",
        },
        {
            "key": "price_strength_score",
            "label": "Koerskracht",
            "description": "Prijsblok: momentum, trend en relatieve sterkte van SOL.",
        },
        {
            "key": "network_usage_score",
            "label": "Gebruik",
            "description": "Netwerk- en DeFi-gebruik op en rond Solana.",
        },
        {
            "key": "capital_flows_score",
            "label": "Kapitaalstromen",
            "description": "TVL en stablecoinvoorraad als kapitaalindicatoren.",
        },
        {
            "key": "ecosystem_breadth_score",
            "label": "Ecosysteembreedte",
            "description": "Hoe breed Solana-ecosysteemtokens meebewegen.",
        },
    ]


def write_overview_outputs(
    dashboard: dict[str, Any],
    backtest: dict[str, Any],
    ledger_payload: dict[str, Any],
    generated: str,
) -> None:
    warnings = []
    if dashboard.get("mode") != "production":
        history = pd.DataFrame()
    else:
        try:
            history = read_signal_research_history()
        except ApiError as exc:
            history = pd.DataFrame()
            warnings = [str(exc)]
    overview_history = build_overview_history(history, generated)
    overview = build_overview(
        dashboard, overview_history["rows"], backtest, ledger_payload, generated
    )
    overview["warnings"].extend(warnings)
    write_json(OVERVIEW_HISTORY_PATH, overview_history)
    write_json(OVERVIEW_PATH, overview)


def build_overview_history(history: pd.DataFrame, generated: str) -> dict[str, Any]:
    if history.empty:
        production = pd.DataFrame()
        legacy_count = 0
    else:
        mode_series = history.get("mode", pd.Series([None] * len(history)))
        legacy_count = int((mode_series != "production").sum())
        production = clean_signal_research_frame(history)
    rows = [overview_history_row(row) for _, row in production.iterrows()]
    return {
        "schema_version": "1.0",
        "generated_at_utc": generated,
        "row_count_total": int(len(production)),
        "legacy_or_nonproduction_rows_preserved": legacy_count,
        "rows": rows,
        "method_transitions": method_transitions(rows),
    }


def overview_history_row(row: pd.Series) -> dict[str, Any]:
    return {
        "run_at_utc": row.get("run_at_utc"),
        "data_cutoff_utc": row.get("data_cutoff_utc"),
        "method_version": row.get("method_version"),
        "sol_price": nullable_float(row.get("sol_price")),
        "current_strength_score": nullable_float(row.get("current_strength_score")),
        "support_score": nullable_float(row.get("support_score")),
        "price_strength_score": nullable_float(row.get("price_strength_score")),
        "network_usage_score": nullable_float(row.get("network_usage_score")),
        "capital_flows_score": nullable_float(row.get("capital_flows_score")),
        "ecosystem_breadth_score": nullable_float(row.get("ecosystem_breadth_score")),
        "regime": row.get("regime"),
        "regime_title": row.get("regime_title"),
    }


def nullable_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def build_overview(
    dashboard: dict[str, Any],
    rows: list[dict[str, Any]],
    backtest: dict[str, Any],
    ledger_payload: dict[str, Any],
    generated: str,
) -> dict[str, Any]:
    current = rows[-1] if rows else current_run_from_dashboard(dashboard)
    previous = rows[-2] if len(rows) >= 2 else None
    warnings = []
    if len(rows) < 2:
        warnings.append("Nog onvoldoende officiële runs voor een vergelijking.")
    drivers = build_driver_changes(current, previous)
    waterfall = build_waterfall(current, previous, drivers)
    track_record = build_track_record(rows, ledger_payload, backtest, dashboard)
    transitions = method_transitions(rows)
    return {
        "schema_version": "1.1",
        "generated_at_utc": generated,
        "current_run": current,
        "previous_run": previous,
        "changes": build_topline_changes(current, previous),
        "drivers": drivers,
        "largest_changes": largest_driver_changes(drivers),
        "waterfall": waterfall,
        "track_record": track_record,
        "method_transitions": transitions,
        "what_would_change": dashboard.get("summary", {}).get("what_would_change", []),
        "warnings": warnings,
    }


def method_transitions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transitions = []
    previous_version = None
    for row in rows:
        version = row.get("method_version")
        if previous_version is not None and version != previous_version:
            meta = method_metadata(version)
            transitions.append(
                {
                    "run_at_utc": row.get("run_at_utc"),
                    "data_cutoff_utc": row.get("data_cutoff_utc"),
                    "previous_version": previous_version,
                    "new_version": version,
                    "label": f"Methode {version} gestart",
                    "description": meta.get("description", "Geen toelichting beschikbaar."),
                }
            )
        previous_version = version
    return transitions


def current_run_from_dashboard(dashboard: dict[str, Any]) -> dict[str, Any]:
    scores = dashboard.get("scores", {})
    blocks = scores.get("blocks", {})
    return {
        "run_at_utc": dashboard.get("generated_at_utc"),
        "data_cutoff_utc": dashboard.get("data_cutoff_utc"),
        "method_version": dashboard.get("method_version"),
        "sol_price": dashboard.get("current", {}).get("sol_price"),
        "current_strength_score": scores.get("market_signal"),
        "support_score": scores.get("evidence_quality"),
        "price_strength_score": blocks.get("price_strength"),
        "network_usage_score": blocks.get("network_usage"),
        "capital_flows_score": blocks.get("capital"),
        "ecosystem_breadth_score": blocks.get("ecosystem_breadth"),
        "regime": dashboard.get("summary", {}).get("regime"),
        "regime_title": dashboard.get("summary", {}).get("regime_title"),
    }


def build_topline_changes(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    if not previous:
        return {
            "market_score_points": None,
            "evidence_score_points": None,
            "sol_price_absolute": None,
            "sol_price_pct": None,
            "available": False,
        }
    return {
        "market_score_points": rounded_or_none(
            score_delta(current, previous, "current_strength_score")
        ),
        "evidence_score_points": rounded_or_none(score_delta(current, previous, "support_score")),
        "sol_price_absolute": rounded_or_none(score_delta(current, previous, "sol_price")),
        "sol_price_pct": rounded_or_none(
            relative_delta(current.get("sol_price"), previous.get("sol_price"))
        ),
        "available": True,
    }


def score_delta(current: dict[str, Any], previous: dict[str, Any], key: str) -> float | None:
    cur = current.get(key)
    prev = previous.get(key)
    if cur is None or prev is None:
        return None
    return float(cur) - float(prev)


def relative_delta(current: Any, previous: Any) -> float | None:
    if current is None or previous in [None, 0]:
        return None
    return (float(current) - float(previous)) / float(previous)


def build_driver_changes(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    current_method = current.get("method_version")
    previous_method = previous.get("method_version") if previous else None
    current_weights = method_weights(current_method)
    previous_weights = method_weights(previous_method)
    comparable = bool(previous) and current_method == previous_method and bool(current_weights)
    drivers = []
    for key, label, score_key in DRIVER_ORDER:
        current_score = nullable_number(current.get(score_key))
        previous_score = nullable_number(previous.get(score_key)) if previous else None
        score_change = (
            None
            if current_score is None or previous_score is None
            else current_score - previous_score
        )
        current_weight = current_weights.get(key)
        previous_weight = previous_weights.get(key) if comparable else None
        current_contribution = weighted_contribution(current_score, current_weight)
        previous_contribution = weighted_contribution(previous_score, previous_weight)
        drivers.append(
            {
                "key": key,
                "label": label,
                "current_score": current_score,
                "previous_score": previous_score,
                "score_delta": rounded_or_none(score_change),
                "current_weight": current_weight,
                "previous_weight": previous_weight,
                "current_contribution": current_contribution,
                "previous_contribution": previous_contribution,
                "contribution_delta": rounded_or_none(
                    None
                    if current_contribution is None or previous_contribution is None
                    else current_contribution - previous_contribution
                ),
                "comparison_status": "comparable"
                if comparable
                else "not_comparable",
                "change_label": change_label(score_change),
            }
        )
    return drivers


def nullable_number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def change_label(delta: float | None) -> str:
    if delta is None:
        return "niet vergelijkbaar"
    magnitude = abs(delta)
    if magnitude < SCORE_CHANGE_THRESHOLDS["unchanged"]:
        return "praktisch onveranderd"
    if magnitude < SCORE_CHANGE_THRESHOLDS["light"]:
        return "licht veranderd"
    if magnitude < SCORE_CHANGE_THRESHOLDS["clear"]:
        return "duidelijk veranderd"
    return "sterk veranderd"


def largest_driver_changes(drivers: list[dict[str, Any]]) -> dict[str, Any]:
    changed = [driver for driver in drivers if driver.get("score_delta") is not None]
    material_changed = [
        driver
        for driver in changed
        if abs(float(driver["score_delta"])) >= SCORE_CHANGE_THRESHOLDS["unchanged"]
    ]
    positive = sorted(
        [driver for driver in material_changed if float(driver["score_delta"]) > 0],
        key=lambda item: item["score_delta"],
        reverse=True,
    )[:2]
    negative = sorted(
        [driver for driver in material_changed if float(driver["score_delta"]) < 0],
        key=lambda item: item["score_delta"],
    )[:2]
    material = [
        driver
        for driver in changed
        if abs(driver["score_delta"]) >= SCORE_CHANGE_THRESHOLDS["light"]
    ]
    if not material:
        conclusion = "Per saldo veranderde het beeld nauwelijks sinds de vorige officiële run."
    else:
        strongest = max(material, key=lambda item: abs(item["score_delta"]))
        direction = "omhoog" if strongest["score_delta"] > 0 else "omlaag"
        conclusion = (
            f"De beweging kwam vooral door {strongest['label'].lower()}, "
            f"dat {direction} trok."
        )
    return {
        "positive": positive,
        "negative": negative,
        "positive_empty_message": None
        if positive
        else "Geen materieel positieve driver sinds de vorige officiële meting.",
        "negative_empty_message": None
        if negative
        else "Geen materieel negatieve driver sinds de vorige officiële meting.",
        "all_unchanged_message": "Het beeld veranderde nauwelijks sinds de vorige officiële meting."
        if not positive and not negative
        else None,
        "conclusion": conclusion,
    }


def build_waterfall(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    drivers: list[dict[str, Any]],
) -> dict[str, Any]:
    if not previous:
        return {
            "available": False,
            "reason_unavailable": "Nog onvoldoende officiële runs voor een waterfall.",
        }
    comparable = all(driver["comparison_status"] == "comparable" for driver in drivers)
    if not comparable:
        return {
            "available": False,
            "reason_unavailable": "De runs zijn methodisch niet betrouwbaar vergelijkbaar.",
            "raw_driver_changes": drivers,
        }
    start = nullable_number(previous.get("current_strength_score"))
    end = nullable_number(current.get("current_strength_score"))
    if start is None or end is None:
        return {
            "available": False,
            "reason_unavailable": "Begin- of eindscore ontbreekt.",
        }
    deltas = [driver.get("contribution_delta") for driver in drivers]
    if any(delta is None for delta in deltas):
        return {
            "available": False,
            "reason_unavailable": "Niet alle gewogen bijdragen zijn beschikbaar.",
        }
    numeric_deltas = [float(delta) for delta in deltas if delta is not None]
    driver_delta_sum = float(sum(numeric_deltas))
    residual = (end - start) - driver_delta_sum
    visible_residual = (
        rounded_or_none(residual)
        if abs(residual) >= WATERFALL_RESIDUAL_VISIBILITY_THRESHOLD
        else 0.0
    )
    raw_steps = waterfall_steps(start, drivers, residual)
    final_end = start + driver_delta_sum + residual
    if abs(final_end - end) > WATERFALL_RECONCILIATION_TOLERANCE:
        return {
            "available": False,
            "reason_unavailable": "Waterfall sluit numeriek niet aan op de totaalscore.",
            "raw_driver_changes": drivers,
        }
    return {
        "available": True,
        "reason_unavailable": None,
        "start_score": rounded_or_none(start),
        "end_score": rounded_or_none(end),
        "driver_delta_sum": rounded_or_none(driver_delta_sum),
        "residual_delta": visible_residual,
        "steps": [rounded_waterfall_step(step) for step in raw_steps],
        "summary": waterfall_summary(drivers),
    }


def waterfall_steps(
    start_score: float,
    drivers: list[dict[str, Any]],
    residual: float,
) -> list[dict[str, Any]]:
    cursor = start_score
    steps = []
    for driver in drivers:
        delta = float(driver["contribution_delta"])
        next_value = cursor + delta
        steps.append(
            {
                "key": driver["key"],
                "label": driver["label"],
                "delta": delta,
                "start": cursor,
                "end": next_value,
                "direction": delta_direction(delta),
                "kind": "driver",
            }
        )
        cursor = next_value
    if abs(residual) >= WATERFALL_RESIDUAL_VISIBILITY_THRESHOLD:
        next_value = cursor + residual
        steps.append(
            {
                "key": "residual",
                "label": "Rest",
                "delta": residual,
                "start": cursor,
                "end": next_value,
                "direction": delta_direction(residual),
                "kind": "residual",
            }
        )
        cursor = next_value
    else:
        cursor += residual
    return steps


def rounded_waterfall_step(step: dict[str, Any]) -> dict[str, Any]:
    rounded = dict(step)
    for key in ["delta", "start", "end"]:
        rounded[key] = rounded_or_none(rounded[key])
    return rounded


def delta_direction(delta: float) -> str:
    if abs(delta) < 1e-12:
        return "neutral"
    return "positive" if delta > 0 else "negative"


def waterfall_summary(drivers: list[dict[str, Any]]) -> str:
    material = [
        driver for driver in drivers if driver.get("contribution_delta") is not None
        and abs(driver["contribution_delta"]) >= 0.1
    ]
    if not material:
        return "De gewogen blokbijdragen veranderden nauwelijks sinds de vorige run."
    up = sorted(
        [d for d in material if d["contribution_delta"] > 0],
        key=lambda d: d["contribution_delta"],
        reverse=True,
    )
    down = sorted(
        [d for d in material if d["contribution_delta"] < 0],
        key=lambda d: d["contribution_delta"],
    )
    parts = []
    if up:
        parts.append(f"omhoog door {up[0]['label'].lower()}")
    if down:
        parts.append(f"omlaag door {down[0]['label'].lower()}")
    return "De score bewoog vooral " + " en ".join(parts) + "."


def build_track_record(
    rows: list[dict[str, Any]],
    ledger_payload: dict[str, Any],
    backtest: dict[str, Any],
    dashboard: dict[str, Any],
) -> dict[str, Any]:
    predictions_raw = ledger_payload.get("predictions", [])
    outcomes = ledger_payload.get("outcomes", [])
    official_signals, legacy_predictions = unique_official_signals(predictions_raw)
    first_signal = official_signals[0] if official_signals else None
    latest_signal = official_signals[-1] if official_signals else None
    horizon_7d = backtest.get("7d", {}) if backtest else {}
    method_versions = sorted(
        {
            str(row.get("method_version"))
            for row in official_signals
            if row.get("method_version")
        }
    )
    official_count = len(official_signals)
    resolved_by_horizon_counts = resolved_by_horizon(outcomes)
    forward_metrics = forward_metrics_by_horizon(official_signals, outcomes)
    resolved_prediction_ids = {
        row.get("prediction_id") for row in outcomes if row.get("prediction_id")
    }
    return {
        "technical_run_count": len(rows),
        "production_run_count": len(rows),
        "first_run_at_utc": rows[0].get("run_at_utc") if rows else None,
        "latest_run_at_utc": rows[-1].get("run_at_utc") if rows else None,
        "calendar_span_days": calendar_span_days(rows[0], rows[-1]) if rows else 0,
        "official_signal_count": official_count,
        "prediction_count": official_count,
        "open_signal_count": max(official_count - len(resolved_prediction_ids), 0),
        "resolved_outcome_count": len(outcomes),
        "resolved_by_horizon": resolved_by_horizon_counts,
        "first_prediction_at_utc": first_signal.get("created_at_utc") if first_signal else None,
        "last_prediction_at_utc": latest_signal.get("created_at_utc") if latest_signal else None,
        "unique_prediction_days": unique_prediction_days(official_signals),
        "legacy_prediction_count": len(legacy_predictions),
        "method_versions": method_versions,
        "method_version_count": len(method_versions),
        "current_method_version": dashboard.get("method_version"),
        "maturity_status": maturity_status(official_count),
        "next_maturity_threshold": next_maturity_threshold(official_count),
        "forward_status": forward_status(len(outcomes)),
        "backtest_status": backtest_status(horizon_7d),
        "forward_metrics": forward_metrics,
        "backtest_metrics": {
            "7d": {
                "prediction_count": horizon_7d.get("prediction_count"),
                "directional_accuracy": horizon_7d.get("directional_accuracy"),
                "brier_score": horizon_7d.get("brier_score"),
                "brier_skill": horizon_7d.get("brier_skill"),
                "calibration_error": horizon_7d.get("calibration_error"),
                "status": backtest_status(horizon_7d),
            }
        },
        "backtest_7d": {
            "prediction_count": horizon_7d.get("prediction_count"),
            "directional_accuracy": horizon_7d.get("directional_accuracy"),
            "brier_score": horizon_7d.get("brier_score"),
            "brier_skill": horizon_7d.get("brier_skill"),
            "calibration_error": horizon_7d.get("calibration_error"),
        },
        "evidence_status": dashboard.get("summary", {}).get("evidence_label"),
        "quality_caps": dashboard.get("scores", {}).get("quality_caps", []),
        "explanation": (
            "Technische updates kunnen meerdere keren per datadag plaatsvinden. Alleen "
            "unieke, vooraf vastgelegde voorspellingen tellen mee als officieel signaal."
        ),
    }


def calendar_span_days(first: dict[str, Any] | None, latest: dict[str, Any] | None) -> int:
    if not first or not latest:
        return 0
    start = pd.to_datetime(first.get("run_at_utc"), utc=True)
    end = pd.to_datetime(latest.get("run_at_utc"), utc=True)
    return int(max((end - start).days, 0))


def maturity_status(count: int) -> str:
    status = MATURITY_THRESHOLDS[0][1]
    for threshold, label in MATURITY_THRESHOLDS:
        if count >= threshold:
            status = label
    return status


def next_maturity_threshold(count: int) -> int | None:
    for threshold, _ in MATURITY_THRESHOLDS:
        if count < threshold:
            return threshold
    return None


def unique_official_signals(
    predictions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    legacy = []
    for prediction in predictions:
        prediction_id = prediction.get("prediction_id")
        if not prediction_id:
            legacy.append(prediction)
            continue
        if prediction_id not in by_id:
            by_id[prediction_id] = prediction
    return sorted(by_id.values(), key=lambda row: str(row.get("created_at_utc", ""))), legacy


def unique_prediction_days(predictions: list[dict[str, Any]]) -> int:
    days = {
        str(prediction.get("data_cutoff_utc", ""))[:10]
        for prediction in predictions
        if prediction.get("data_cutoff_utc")
    }
    return len(days)


def forward_status(outcome_count: int) -> str:
    if outcome_count == 0:
        return "Nog geen afgeronde publieke voorspellingen."
    if outcome_count < 10:
        return "Nog onvoldoende afgeronde publieke voorspellingen."
    if outcome_count < 30:
        return "Eerste indicatieve forwardresultaten; steekproef blijft beperkt."
    if outcome_count < 100:
        return "Forward-trackrecord in opbouw."
    return "Structurele forwardevaluatie mogelijk."


def backtest_status(horizon_7d: dict[str, Any]) -> str:
    predictions = horizon_7d.get("prediction_count") or 0
    skill = horizon_7d.get("brier_skill")
    calibration = horizon_7d.get("calibration_error")
    if predictions < 30:
        return "Onvoldoende historische voorspellingen."
    if skill is None or skill <= 0:
        return "Niet beter dan de basislijn."
    if skill > 0.05 and (calibration is None or calibration <= 0.08) and predictions >= 100:
        return "Historisch stabiele meerwaarde over voldoende perioden."
    if skill > 0.05:
        return "Positieve historische meerwaarde, maar steekproef blijft beperkt."
    return "Lichte historische meerwaarde."


def forward_metrics_by_horizon(
    predictions: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    predictions_by_id = {row.get("prediction_id"): row for row in predictions}
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for outcome in outcomes:
        prediction = predictions_by_id.get(outcome.get("prediction_id"))
        if not prediction:
            continue
        horizon = str(outcome.get("horizon") or "onbekend")
        grouped.setdefault(horizon, []).append((prediction, outcome))
    return {horizon: forward_metric(values) for horizon, values in grouped.items()}


def forward_metric(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    if not rows:
        return {"resolved_count": 0}
    directions = []
    brier_values = []
    returns = []
    for prediction, outcome in rows:
        actual_direction = bool(outcome.get("actual_direction"))
        predicted_probability = predicted_positive_probability(prediction, outcome.get("horizon"))
        if predicted_probability is not None:
            directions.append((predicted_probability >= 0.5) == actual_direction)
            brier_values.append((predicted_probability - float(actual_direction)) ** 2)
        if outcome.get("actual_return") is not None:
            returns.append(float(outcome["actual_return"]))
    return {
        "resolved_count": len(rows),
        "directional_accuracy": round(sum(directions) / len(directions), 4)
        if directions
        else None,
        "brier_score": round(sum(brier_values) / len(brier_values), 4)
        if brier_values
        else None,
        "average_return": round(sum(returns) / len(returns), 4) if returns else None,
        "median_return": round(float(pd.Series(returns).median()), 4) if returns else None,
    }


def predicted_positive_probability(prediction: dict[str, Any], horizon: Any) -> float | None:
    horizon_data = (prediction.get("horizons") or {}).get(str(horizon), {})
    probability = horizon_data.get("positive_frequency")
    if probability is None:
        return None
    return float(probability)


def resolved_by_horizon(outcomes: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        horizon = str(outcome.get("horizon") or "onbekend")
        counts[horizon] = counts.get(horizon, 0) + 1
    return counts


def write_all_json(
    dashboard: dict[str, Any],
    df: pd.DataFrame,
    analogs: pd.DataFrame,
    backtest: dict[str, Any],
    source_status: dict[str, Any],
    interpretation: dict[str, Any],
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
    ledger_payload = {
        "schema_version": "1.0",
        "generated_at_utc": generated,
        "method_version": method,
        "predictions": read_jsonl(ROOT / "data/ledger/predictions.jsonl"),
        "outcomes": read_jsonl(ROOT / "data/ledger/outcomes.jsonl"),
    }
    write_json(
        SITE_DATA / "ledger.json",
        ledger_payload,
    )
    write_overview_outputs(dashboard, backtest, ledger_payload, generated)
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
    write_json(SITE_DATA / "interpretation.json", interpretation)
    write_interpretation_archive(interpretation)
    write_json(
        SITE_DATA / "build_info.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": generated,
            "data_cutoff_utc": cutoff,
            "method_version": method,
        },
    )


def write_interpretation_archive(interpretation: dict[str, Any]) -> None:
    archive_dir = SITE_DATA / "interpretations"
    archive_dir.mkdir(parents=True, exist_ok=True)
    interpretation_date = str(
        interpretation.get("interpretation_date")
        or str(interpretation.get("data_cutoff_utc", ""))[:10]
    )
    if not interpretation_date:
        return
    daily_payload = {
        "schema_version": "1.0",
        "date": interpretation_date,
        "generated_at_utc": interpretation.get("generated_at_utc"),
        "data_cutoff_utc": interpretation.get("data_cutoff_utc"),
        "llm_called_at_utc": interpretation.get("llm_called_at_utc"),
        "status": interpretation.get("status"),
        "provider": interpretation.get("provider"),
        "model": interpretation.get("model"),
        "title": interpretation.get("title"),
        "intro": interpretation.get("intro"),
        "analysis_text": interpretation.get("analysis_text"),
        "warnings": interpretation.get("warnings", []),
        "footer_note": interpretation.get("footer_note"),
        "input_snapshot": interpretation.get("input_snapshot", {}),
    }
    write_json(archive_dir / f"{interpretation_date}.json", daily_payload)
    index_path = archive_dir / "index.json"
    existing_entries = []
    if index_path.exists():
        try:
            existing_entries = json.loads(index_path.read_text(encoding="utf-8")).get(
                "entries", []
            )
        except json.JSONDecodeError:
            existing_entries = []
    entry = {
        "date": interpretation_date,
        "title": interpretation.get("title"),
        "status": interpretation.get("status"),
        "market_signal": (interpretation.get("input_snapshot") or {}).get("market_signal"),
        "evidence_quality": (interpretation.get("input_snapshot") or {}).get(
            "evidence_quality"
        ),
        "generated_at_utc": interpretation.get("generated_at_utc"),
        "llm_called_at_utc": interpretation.get("llm_called_at_utc"),
        "model": interpretation.get("model"),
        "path": f"./data/interpretations/{interpretation_date}.json",
    }
    entries_by_date = {
        str(item.get("date")): item for item in existing_entries if item.get("date")
    }
    entries_by_date[interpretation_date] = entry
    entries = sorted(entries_by_date.values(), key=lambda item: item["date"], reverse=True)
    write_json(
        index_path,
        {
            "schema_version": "1.0",
            "generated_at_utc": interpretation.get("generated_at_utc"),
            "entries": entries,
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
