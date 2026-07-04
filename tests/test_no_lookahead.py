import pandas as pd

from sol_reality_check.analytics import add_features, robust_z_scores
from sol_reality_check.demo import demo_history


def test_future_extreme_values_do_not_change_historical_scores():
    base = add_features(demo_history(days=900))
    features = ["sol_return_7d", "relative_strength_btc_7d", "price_vs_sma50"]
    scored = robust_z_scores(base, features, window=300, min_obs=100)
    changed = base.copy()
    changed.loc[700:, "sol_return_7d"] = 999
    changed.loc[700:, "relative_strength_btc_7d"] = 999
    changed.loc[700:, "price_vs_sma50"] = 999
    rescored = robust_z_scores(changed, features, window=300, min_obs=100)
    pd.testing.assert_frame_equal(scored.loc[:650], rescored.loc[:650])
