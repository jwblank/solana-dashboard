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
    assert waterfall["steps"][0]["label"] == "Koerskracht"
    assert math.isclose(
        waterfall["steps"][1]["start"],
        waterfall["steps"][0]["end"],
        abs_tol=0.01,
    )


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


def driver(label, delta):
    return {
        "label": label,
        "score_delta": delta,
        "contribution_delta": delta,
    }


def test_largest_driver_changes_filters_positive_and_negative():
    result = pipeline.largest_driver_changes(
        [
            driver("A", 4.0),
            driver("B", 2.0),
            driver("C", -3.0),
            driver("D", -1.0),
        ]
    )
    assert [item["label"] for item in result["positive"]] == ["A", "B"]
    assert [item["label"] for item in result["negative"]] == ["C", "D"]
    assert all(item["score_delta"] > 0 for item in result["positive"])
    assert all(item["score_delta"] < 0 for item in result["negative"])


def test_largest_driver_changes_handles_no_positive_drivers():
    result = pipeline.largest_driver_changes(
        [driver("A", -4.0), driver("B", -2.0), driver("C", -0.1)]
    )
    assert result["positive"] == []
    assert "Geen materieel positieve" in result["positive_empty_message"]
    assert len(result["negative"]) == 2


def test_largest_driver_changes_handles_no_negative_drivers():
    result = pipeline.largest_driver_changes(
        [driver("A", 4.0), driver("B", 2.0), driver("C", 0.1)]
    )
    assert result["negative"] == []
    assert "Geen materieel negatieve" in result["negative_empty_message"]
    assert len(result["positive"]) == 2


def test_largest_driver_changes_ignores_null_and_tiny_changes():
    result = pipeline.largest_driver_changes(
        [driver("A", 0.1), driver("B", -0.2), driver("C", None)]
    )
    assert result["positive"] == []
    assert result["negative"] == []
    assert result["all_unchanged_message"]


def test_waterfall_not_available_when_block_score_missing():
    previous = row("2026-07-08T10:00:00Z", 51.0)
    current = row("2026-07-09T10:00:00Z", 54.0)
    current["network_usage_score"] = None
    drivers = pipeline.build_driver_changes(current, previous)
    waterfall = pipeline.build_waterfall(current, previous, drivers)
    assert waterfall["available"] is False
    assert "gewogen bijdragen" in waterfall["reason_unavailable"]


def test_waterfall_hides_tiny_residual_but_still_reconciles():
    previous = row("2026-07-08T10:00:00Z", 51.0)
    current = row("2026-07-09T10:00:00Z", 51.01)
    drivers = pipeline.build_driver_changes(current, previous)
    waterfall = pipeline.build_waterfall(current, previous, drivers)
    assert waterfall["available"] is True
    assert waterfall["residual_delta"] == 0.0


def test_forward_status_is_independent_from_backtest():
    assert pipeline.forward_status(0) == "Nog geen afgeronde publieke voorspellingen."
    assert pipeline.forward_status(5) == "Nog onvoldoende afgeronde publieke voorspellingen."
    assert pipeline.forward_status(30) == "Forward-trackrecord in opbouw."
    strong_backtest = {"prediction_count": 130, "brier_skill": 0.2}
    weak_backtest = {"prediction_count": 130, "brier_skill": -0.2}
    assert pipeline.forward_status(0) == pipeline.forward_status(0)
    assert pipeline.backtest_status(strong_backtest) != pipeline.backtest_status(weak_backtest)


def test_track_record_counts_official_signals_not_technical_runs():
    rows = [
        row("2026-07-08T10:00:00Z", 51.0),
        row("2026-07-08T10:05:00Z", 51.0),
    ]
    ledger = {
        "predictions": [
            {
                "prediction_id": "2026-07-07__method-v1.0.0",
                "created_at_utc": "2026-07-08T10:00:00Z",
                "data_cutoff_utc": "2026-07-07T23:59:59Z",
                "method_version": "1.0.0",
            },
            {
                "prediction_id": "2026-07-07__method-v1.0.0",
                "created_at_utc": "2026-07-08T10:05:00Z",
                "data_cutoff_utc": "2026-07-07T23:59:59Z",
                "method_version": "1.0.0",
            },
            {"created_at_utc": "legacy"},
        ],
        "outcomes": [],
    }
    track = pipeline.build_track_record(rows, ledger, {"7d": {}}, {"method_version": "1.0.0"})
    assert track["technical_run_count"] == 2
    assert track["official_signal_count"] == 1
    assert track["legacy_prediction_count"] == 1
    assert track["maturity_status"] == "Startfase"


def test_method_transitions_include_old_and_new_version():
    rows = [
        row("2026-07-08T10:00:00Z", 51.0, method="1.0.0"),
        row("2026-07-09T10:00:00Z", 51.0, method="1.1.0"),
    ]
    transitions = pipeline.method_transitions(rows)
    assert transitions[0]["previous_version"] == "1.0.0"
    assert transitions[0]["new_version"] == "1.1.0"
    assert transitions[0]["run_at_utc"] == "2026-07-09T10:00:00Z"
