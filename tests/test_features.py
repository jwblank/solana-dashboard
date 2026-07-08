import numpy as np
import pandas as pd

from sol_reality_check.analytics import add_features
from sol_reality_check.demo import demo_history
from sol_reality_check.pipeline import (
    ApiError,
    assert_price_coverage,
    coinbase_gap_fill_breakdown,
    first_missing_daily_date,
    production_history_cache_is_usable,
    repair_history_prices,
)


def test_feature_engineering_core_columns():
    df = add_features(demo_history(days=260))
    latest = df.iloc[-1]
    assert np.isfinite(latest["sol_return_7d"])
    assert np.isfinite(latest["relative_strength_btc_30d"])
    assert np.isfinite(latest["price_vs_sma50"])
    assert np.isfinite(latest["realized_volatility_30d"])
    assert np.isfinite(latest["drawdown_90d"])


def test_repair_history_prices_replaces_extreme_sol_close_outlier():
    dates = pd.date_range("2026-06-01", periods=36, freq="D").date.astype(str)
    history = pd.DataFrame(
        {
            "date": dates,
            "sol_close": [137.0] * 35 + [29.5],
            "sol_volume": [1_000_000.0] * 36,
            "btc_close": [100_000.0] * 36,
            "tvl": [1_000_000_000.0] * 36,
            "stablecoins": [1_000_000_000.0] * 36,
            "dex_volume": [10_000_000.0] * 36,
            "fees": [100_000.0] * 36,
        }
    )

    repaired = repair_history_prices(history)
    features = add_features(repaired)

    assert repaired.iloc[-1]["sol_close"] == 137.0
    assert repaired.attrs["price_repairs"][0]["date"] == "2026-07-06"
    assert repaired.attrs["price_repairs"][0]["replacement_close"] == 137.0
    assert features.iloc[-1]["sol_return_30d"] == 0.0


def test_repair_history_prices_keeps_trusted_consensus_date():
    dates = pd.date_range("2026-06-01", periods=36, freq="D").date.astype(str)
    history = pd.DataFrame(
        {
            "date": dates,
            "sol_close": [137.0] * 35 + [79.5],
            "sol_volume": [1_000_000.0] * 36,
            "btc_close": [100_000.0] * 36,
            "tvl": [1_000_000_000.0] * 36,
            "stablecoins": [1_000_000_000.0] * 36,
            "dex_volume": [10_000_000.0] * 36,
            "fees": [100_000.0] * 36,
        }
    )

    repaired = repair_history_prices(history, {"sol_close": {"2026-07-06"}})

    assert repaired.iloc[-1]["sol_close"] == 79.5
    assert "price_repairs" not in repaired.attrs


def test_repair_history_prices_repairs_absurd_trusted_consensus_date():
    dates = pd.date_range("2024-07-14", periods=4, freq="D").date.astype(str)
    history = pd.DataFrame(
        {
            "date": dates,
            "sol_close": [140.0, 141.0, 142.0, 1_134.0],
            "sol_volume": [1_000_000.0] * 4,
            "btc_close": [60_000.0] * 4,
            "tvl": [1_000_000_000.0] * 4,
            "stablecoins": [1_000_000_000.0] * 4,
            "dex_volume": [10_000_000.0] * 4,
            "fees": [100_000.0] * 4,
        }
    )

    repaired = repair_history_prices(history, {"sol_close": {"2024-07-17"}})

    assert repaired.iloc[-1]["sol_close"] == 142.0
    assert repaired.attrs["price_repairs"][0]["date"] == "2024-07-17"


def test_repair_history_prices_trusts_cached_consensus_metadata():
    dates = pd.date_range("2026-06-01", periods=36, freq="D").date.astype(str)
    history = pd.DataFrame(
        {
            "date": dates,
            "sol_close": [137.0] * 35 + [79.5],
            "sol_price_source_count": [1] * 35 + [4],
            "sol_volume": [1_000_000.0] * 36,
            "btc_close": [100_000.0] * 36,
            "tvl": [1_000_000_000.0] * 36,
            "stablecoins": [1_000_000_000.0] * 36,
            "dex_volume": [10_000_000.0] * 36,
            "fees": [100_000.0] * 36,
        }
    )

    repaired = repair_history_prices(history)

    assert repaired.iloc[-1]["sol_close"] == 79.5
    assert "price_repairs" not in repaired.attrs


def test_production_cache_requires_price_source_metadata():
    history = demo_history(days=40)

    usable, reason = production_history_cache_is_usable(history)

    assert usable is False
    assert "missing price source metadata" in reason


def test_production_cache_rejects_extreme_price_break_even_with_metadata():
    dates = pd.date_range("2026-06-01", periods=5, freq="D").date.astype(str)
    history = pd.DataFrame(
        {
            "date": dates,
            "sol_close": [137.0, 138.0, 139.0, 140.0, 71.0],
            "sol_price_source_count": [1] * 5,
            "sol_price_sources": ["coinbase"] * 5,
            "btc_close": [100_000.0] * 5,
            "btc_price_source_count": [4] * 5,
            "btc_price_sources": ["coinbase,kraken,kucoin,okx"] * 5,
        }
    )

    usable, reason = production_history_cache_is_usable(history)

    assert usable is False
    assert "sol_close daily break" in reason


def test_production_cache_allows_extreme_price_break_with_trusted_consensus_metadata():
    dates = pd.date_range("2022-11-06", periods=5, freq="D").date.astype(str)
    history = pd.DataFrame(
        {
            "date": dates,
            "sol_close": [32.0, 31.0, 30.0, 17.4, 18.0],
            "sol_price_source_count": [4] * 5,
            "sol_price_sources": ["coinbase,kraken,kucoin,okx"] * 5,
            "btc_close": [20_000.0] * 5,
            "btc_price_source_count": [4] * 5,
            "btc_price_sources": ["coinbase,kraken,kucoin,okx"] * 5,
        }
    )

    usable, reason = production_history_cache_is_usable(history)

    assert usable is True
    assert reason == ""


def test_production_cache_rejects_absurd_price_break_even_with_trusted_metadata():
    dates = pd.date_range("2024-07-14", periods=4, freq="D").date.astype(str)
    history = pd.DataFrame(
        {
            "date": dates,
            "sol_close": [140.0, 141.0, 142.0, 1_134.0],
            "sol_price_source_count": [4] * 4,
            "sol_price_sources": ["coinbase,kraken,kucoin,okx"] * 4,
            "btc_close": [60_000.0] * 4,
            "btc_price_source_count": [4] * 4,
            "btc_price_sources": ["coinbase,kraken,kucoin,okx"] * 4,
        }
    )

    usable, reason = production_history_cache_is_usable(history)

    assert usable is False
    assert "sol_close daily break" in reason


def test_price_coverage_rejects_short_consensus_for_full_rebuild():
    frame = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=8).date.astype(str)})

    try:
        assert_price_coverage(frame, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01"), 0.8)
    except ApiError as exc:
        assert "insufficient history" in str(exc)
    else:
        raise AssertionError("Expected insufficient history failure")


def test_price_coverage_accepts_partial_history_when_method_has_enough_rows():
    frame = pd.DataFrame({"date": pd.date_range("2023-09-20", periods=1020).date.astype(str)})

    assert_price_coverage(
        frame,
        pd.Timestamp("2022-09-06"),
        pd.Timestamp("2026-07-07"),
        0.8,
        min_required_rows=395,
    )


def test_first_missing_daily_date_detects_history_gap():
    frame = pd.DataFrame({"date": ["2026-01-01", "2026-01-02", "2026-01-04"]})

    missing = first_missing_daily_date(
        frame,
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-01-06"),
    )

    assert missing == "2026-01-03"


def test_first_missing_daily_date_returns_none_for_complete_history():
    frame = pd.DataFrame(
        {"date": pd.date_range("2026-01-01", periods=5, freq="D").date.astype(str)}
    )

    missing = first_missing_daily_date(
        frame,
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-01-06"),
    )

    assert missing is None


def test_coinbase_gap_fill_breakdown_uses_last_ccxt_day_before_gap():
    ccxt = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02", "2026-01-04"],
            "close": [100.0, 101.0, 150.0],
        }
    )
    coinbase = pd.DataFrame(
        {
            "date": ["2026-01-03", "2026-01-04"],
            "asset": ["SOL", "SOL"],
            "close": [102.0, 103.0],
        }
    )

    breakdown = coinbase_gap_fill_breakdown(coinbase, ccxt, "2026-01-03")

    assert breakdown["used_close"] == 103.0
    assert breakdown["ccxt_last_date"] == "2026-01-02"
    assert breakdown["ccxt_last_close"] == 101.0
