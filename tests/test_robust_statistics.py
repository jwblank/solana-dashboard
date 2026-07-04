import pandas as pd

from sol_reality_check.analytics import robust_z_scores


def test_robust_z_uses_only_past_data():
    df = pd.DataFrame({"x": list(range(250))})
    base = robust_z_scores(df, ["x"], window=200, min_obs=50)
    changed = df.copy()
    changed.loc[220:, "x"] = 10_000
    altered = robust_z_scores(changed, ["x"], window=200, min_obs=50)
    pd.testing.assert_series_equal(base.loc[:199, "x__z"], altered.loc[:199, "x__z"])


def test_mad_zero_is_safe():
    df = pd.DataFrame({"x": [1] * 250})
    scores = robust_z_scores(df, ["x"], window=200, min_obs=50)
    assert scores["x__score"].isna().all()
