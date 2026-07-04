import numpy as np

from sol_reality_check.analytics import add_features
from sol_reality_check.demo import demo_history


def test_feature_engineering_core_columns():
    df = add_features(demo_history(days=260))
    latest = df.iloc[-1]
    assert np.isfinite(latest["sol_return_7d"])
    assert np.isfinite(latest["relative_strength_btc_30d"])
    assert np.isfinite(latest["price_vs_sma50"])
    assert np.isfinite(latest["realized_volatility_30d"])
    assert np.isfinite(latest["drawdown_90d"])
