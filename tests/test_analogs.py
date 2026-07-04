from sol_reality_check.analytics import add_features, analog_summary, find_analogs, robust_z_scores
from sol_reality_check.demo import demo_history


def prepared():
    df = add_features(demo_history(days=900))
    features = ["sol_return_7d", "sol_return_30d", "relative_strength_btc_7d"]
    return df.join(robust_z_scores(df, features, window=300, min_obs=100)), {f: 1 for f in features}


def test_analogs_are_past_and_spaced():
    df, weights = prepared()
    analogs = find_analogs(df, 850, weights, horizon=7, max_count=20, min_spacing=7)
    assert len(analogs) <= 20
    assert all(analogs.index < 843)
    assert analogs.index.to_series().diff().abs().dropna().ge(7).all()


def test_analog_summary_has_uncertainty():
    df, weights = prepared()
    analogs = find_analogs(df, 850, weights, horizon=7)
    summary = analog_summary(analogs, 7)
    assert "wilson_low" in summary
    assert summary["count"] > 0
