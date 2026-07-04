from sol_reality_check.analytics import evidence_quality, regime, score_label, weighted_average


def test_weighted_average_renormalizes_missing_values():
    score, missing = weighted_average({"a": 80, "b": None}, {"a": 0.5, "b": 0.5})
    assert score == 80
    assert missing == ["b"]


def test_regime_boundaries_do_not_force_neutral():
    key, _ = regime(52, 80, 80)
    assert key == "mixed"


def test_quality_caps_apply():
    quality = evidence_quality(
        90,
        {"count": 10, "median_similarity": 80},
        {"7d": {"brier_skill": -0.1, "prediction_count": 50}},
        80,
    )
    assert quality["score"] <= 45
    assert quality["caps"]


def test_score_label():
    assert score_label(74) == "sterk positief"
    assert score_label(50) == "neutraal of gemengd"
