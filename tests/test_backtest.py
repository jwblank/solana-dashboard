from sol_reality_check.analytics import add_features, robust_z_scores, run_backtest
from sol_reality_check.demo import demo_history


def test_backtest_produces_horizon_metrics():
    df = add_features(demo_history(days=850))
    features = ["sol_return_7d", "sol_return_30d", "relative_strength_btc_7d"]
    df = df.join(robust_z_scores(df, features, window=300, min_obs=100))
    result = run_backtest(df.assign(regime="mixed"), {f: 1 for f in features}, [1, 7])
    assert "7d" in result.summary
    assert result.summary["7d"]["prediction_count"] > 0
