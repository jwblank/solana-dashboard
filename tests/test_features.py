import numpy as np
import pandas as pd

from sol_reality_check.analytics import add_features
from sol_reality_check.demo import demo_history
from sol_reality_check.pipeline import (
    ApiError,
    assert_price_coverage,
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
            "sol_price_source_count": [4] * 5,
            "sol_price_sources": ["coinbase,kraken,kucoin,okx"] * 5,
            "btc_close": [100_000.0] * 5,
            "btc_price_source_count": [4] * 5,
            "btc_price_sources": ["coinbase,kraken,kucoin,okx"] * 5,
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
