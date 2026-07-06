from sol_reality_check.llm_interpretation import (
    build_interpretation,
    complete_required_values,
    interpretation_facts,
    parse_llm_response,
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
    assert result["interpretation_date"] == "2026-07-05"
    body = " ".join([result["intro"], result["analysis_text"]])
    for value in ["70/100", "55/100", "48/100", "94/100", "100/100", "62/100"]:
        assert value in body


def test_validate_llm_output_requires_dashboard_values():
    facts = interpretation_facts(sample_dashboard(), {"7d": {}})
    data = {
        "title": "Duiding",
        "intro": "Marktsignaal 70/100 en bewijskwaliteit 55/100.",
        "analysis_text": "Geen concrete blokscore.",
    }
    try:
        validate_llm_output(data, facts)
    except ValueError as exc:
        assert "dashboardwaarden" in str(exc)
    else:
        raise AssertionError("Expected validation failure")


def test_parse_marked_llm_output_validates_dashboard_values():
    facts = interpretation_facts(sample_dashboard(), {"7d": {}})
    parsed = parse_llm_response(
        """
TITEL: Onderliggende kracht bouwt op
ANALYSE: Marktsignaal 70/100 en bewijskwaliteit 55/100 geven een positief maar
beperkt bewezen beeld. SOL staat rond $81.23. Prijssterkte 48/100,
netwerkgebruik 94/100, kapitaal 100/100 en ecosysteembreedte 62/100 lopen niet
gelijk. De historische vergelijking gebruikt 40 dagen en 45.0% was positief.
"""
    )

    validated = validate_llm_output(parsed, facts)

    assert validated["title"] == "Onderliggende kracht bouwt op"
    assert "kapitaal 100/100" in validated["analysis_text"]


def test_parse_legacy_markdown_output_without_title_or_intro_uses_facts():
    facts = interpretation_facts(sample_dashboard(), {"7d": {}})
    parsed = parse_llm_response(
        """
## Kort beeld
SOL staat rond $81.23. Marktsignaal 70/100 en bewijskwaliteit 55/100 geven context.
## Wat valt op?
Prijssterkte 48/100, netwerkgebruik 94/100, kapitaal 100/100 en
ecosysteembreedte 62/100 lopen uiteen.
## Wat ondersteunt het beeld?
De historische vergelijking gebruikt 40 vergelijkbare dagen; 45.0% was positief.
## Wat maakt het onzeker?
Bewijskwaliteit 55/100 betekent dat het bewijs beperkt blijft.
## Eindbeeld
Met marktsignaal 70/100, prijssterkte 48/100, netwerkgebruik 94/100,
kapitaal 100/100 en ecosysteembreedte 62/100 is het beeld bruikbaar.
""",
        facts,
    )

    validated = validate_llm_output(parsed, facts)

    assert validated["title"] == "Onderliggende kracht bouwt op"
    assert "70/100" in validated["intro"]
    assert "55/100" in validated["intro"]
    assert "kapitaal 100/100" in validated["analysis_text"]


def test_parse_numbered_legacy_output_sections():
    facts = interpretation_facts(sample_dashboard(), {"7d": {}})
    parsed = parse_llm_response(
        """
TITEL: Brede maar beperkte bevestiging
INTRO: Marktsignaal 70/100 en bewijskwaliteit 55/100 vragen om nuance.
1. Kort beeld
SOL staat rond $81.23 en het marktsignaal 70/100 is positief.
2. Wat valt op?
Prijssterkte 48/100, netwerkgebruik 94/100, kapitaal 100/100 en
ecosysteembreedte 62/100 staan niet gelijk.
3. Wat ondersteunt het beeld?
Historische analogieën tellen 40 dagen en 45.0% was positief.
4. Wat maakt het onzeker?
Bewijskwaliteit 55/100 maakt het signaal niet hard.
5. Eindbeeld
Marktsignaal 70/100, prijssterkte 48/100, netwerkgebruik 94/100,
kapitaal 100/100 en ecosysteembreedte 62/100 geven samen het beeld.
""",
        facts,
    )

    validated = validate_llm_output(parsed, facts)

    assert "kapitaal 100/100" in validated["analysis_text"]


def test_complete_required_values_adds_missing_dashboard_value():
    facts = interpretation_facts(sample_dashboard(), {"7d": {}})
    data = {
        "title": "Duiding",
        "intro": "Marktsignaal 70/100 en bewijskwaliteit 55/100.",
        "analysis_text": (
            "Prijssterkte 48/100, netwerkgebruik 94/100 en ecosysteembreedte 62/100 "
            "staan in beeld."
        ),
    }

    completed, warnings = complete_required_values(data, facts)
    validated = validate_llm_output(completed, facts)

    assert warnings
    assert "kapitaal 100/100" in validated["analysis_text"]
