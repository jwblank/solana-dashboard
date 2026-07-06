from sol_reality_check.llm_interpretation import (
    FIXED_HEADINGS,
    build_interpretation,
    interpretation_facts,
    validate_llm_output,
)


def sample_dashboard():
    return {
        "generated_at_utc": "2026-07-06T07:00:00Z",
        "data_cutoff_utc": "2026-07-05T23:59:59Z",
        "method_version": "1.0.0",
        "summary": {
            "regime_title": "Onderliggende kracht bouwt op",
            "market_signal_label": "sterk positief",
            "evidence_label": "beperkt bewijs",
        },
        "scores": {
            "market_signal": 70,
            "evidence_quality": 55,
            "blocks": {
                "price_strength": 48,
                "network_usage": 94,
                "capital": 100,
                "ecosystem_breadth": 62,
            },
            "block_weights": {
                "price_strength": 0.45,
                "network_usage": 0.25,
                "capital": 0.20,
                "ecosystem_breadth": 0.10,
            },
        },
        "current": {"sol_price": 81.23},
        "analog_summary": {
            "count": 40,
            "positive_frequency": 0.45,
            "median_return": -0.011,
        },
        "historical_context": {"summary": "Historische analogieën zijn gemengd."},
        "indicator_tabs": {
            "price": {"summary": "Prijs is gemengd.", "components": []},
            "network": {"summary": "Netwerk is sterk.", "components": []},
            "capital": {"summary": "Kapitaal is sterk.", "components": []},
        },
        "data_audit": {"summary": "Bronnen zijn actueel.", "freshness": [], "warnings": []},
    }


def test_build_interpretation_falls_back_without_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    result = build_interpretation(sample_dashboard(), {"7d": {}}, "2026-07-06T07:00:00Z")
    assert result["status"] == "fallback_no_token"
    assert result["llm_called_at_utc"] is None
    assert [section["heading"] for section in result["sections"]] == FIXED_HEADINGS
    body = " ".join([result["intro"], *(section["text"] for section in result["sections"])])
    for value in ["70/100", "55/100", "48/100", "94/100", "100/100", "62/100"]:
        assert value in body


def test_validate_llm_output_requires_dashboard_values():
    facts = interpretation_facts(sample_dashboard(), {"7d": {}})
    data = {
        "title": "Duiding",
        "intro": "Marktsignaal 70/100 en bewijskwaliteit 55/100.",
        "sections": [
            {"heading": heading, "text": "Geen concrete blokscore."} for heading in FIXED_HEADINGS
        ],
    }
    try:
        validate_llm_output(data, facts)
    except ValueError as exc:
        assert "dashboardwaarden" in str(exc)
    else:
        raise AssertionError("Expected validation failure")
