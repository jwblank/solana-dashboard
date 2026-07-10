import math

from sol_reality_check import pipeline


def row(run, score, support=55.0, price=80.0, method="1.0.0"):
    return {
        "run_at_utc": run,
        "data_cutoff_utc": "2026-07-07T23:59:59Z",
        "method_version": method,
        "sol_price": price,
        "current_strength_score": score,
        "support_score": support,
        "price_strength_score": 60.0,
        "network_usage_score": 55.0,
        "capital_flows_score": 50.0,
        "ecosystem_breadth_score": 58.0,
        "regime": "mixed",
        "regime_title": "Gemengd marktbeeld",
    }


def test_change_label_thresholds():
    assert pipeline.change_label(0.1) == "praktisch onveranderd"
    assert pipeline.change_label(1.0) == "licht veranderd"
    assert pipeline.change_label(3.0) == "duidelijk veranderd"
    assert pipeline.change_label(6.0) == "sterk veranderd"


def test_overview_handles_single_run_without_fake_change():
    rows = [row("2026-07-08T10:00:00Z", 51.0)]
    overview = pipeline.build_overview(
        {"method_version": "1.0.0", "summary": {}, "scores": {}},
        rows,
        {},
        {"predictions": [], "outcomes": []},
        "2026-07-08T10:00:00Z",
    )
    assert overview["previous_run"] is None
    assert overview["changes"]["available"] is False
    assert overview["waterfall"]["available"] is False
    assert "Nog onvoldoende" in overview["warnings"][0]


def test_waterfall_reconciles_to_total_delta():
    previous = row("2026-07-08T10:00:00Z", 51.0, price=80.0)
    current = row("2026-07-09T10:00:00Z", 54.0, price=82.0)
    current["price_strength_score"] = 64.0
    current["network_usage_score"] = 57.0
    current["capital_flows_score"] = 52.0
    current["ecosystem_breadth_score"] = 59.0
    drivers = pipeline.build_driver_changes(current, previous)
    waterfall = pipeline.build_waterfall(current, previous, drivers)
    assert waterfall["available"] is True
    reconstructed = (
        waterfall["start_score"]
        + waterfall["driver_delta_sum"]
        + waterfall["residual_delta"]
    )
    assert math.isclose(reconstructed, waterfall["end_score"], abs_tol=0.06)


def test_waterfall_not_available_for_method_version_change():
    previous = row("2026-07-08T10:00:00Z", 51.0, method="1.0.0")
    current = row("2026-07-09T10:00:00Z", 54.0, method="2.0.0")
    drivers = pipeline.build_driver_changes(current, previous)
    waterfall = pipeline.build_waterfall(current, previous, drivers)
    assert waterfall["available"] is False
    assert "methodisch" in waterfall["reason_unavailable"]


def test_maturity_boundaries():
    assert pipeline.maturity_status(0) == "Startfase"
    assert pipeline.maturity_status(29) == "Startfase"
    assert pipeline.maturity_status(30) == "Opbouwfase"
    assert pipeline.maturity_status(100) == "Eerste structurele evaluatie mogelijk"
    assert pipeline.maturity_status(250) == "Volwassen publiek trackrecord"


def test_performance_status_is_conservative_for_small_samples():
    status = pipeline.performance_status(2, {"prediction_count": 130, "brier_skill": 0.2})
    assert status == "Nog onvoldoende afgeronde uitkomsten."
    status = pipeline.performance_status(50, {"prediction_count": 130, "brier_skill": -0.1})
    assert status == "Nog geen aantoonbare meerwaarde boven de basislijn."
