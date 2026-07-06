import numpy as np
import pandas as pd

from sol_reality_check.analytics import add_features
from sol_reality_check.demo import demo_history
from sol_reality_check.pipeline import repair_history_prices


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
