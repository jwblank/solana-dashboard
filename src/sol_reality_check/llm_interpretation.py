from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import Any

from sol_reality_check.clients import ApiError, HttpClient
from sol_reality_check.utils import iso_z

DEFAULT_PROVIDER = "Hugging Face Inference Providers"
DEFAULT_MODEL = "Qwen/Qwen3-8B"
ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
FIXED_HEADINGS = [
    "Kort beeld",
    "Wat valt op?",
    "Wat ondersteunt het beeld?",
    "Wat maakt het onzeker?",
    "Eindbeeld",
]
FORBIDDEN_TERMS = [
    "koop",
    "kopen",
    "verkoop",
    "verkopen",
    "long",
    "short",
    "garantie",
    "zeker rendement",
]


def build_interpretation(
    dashboard: dict[str, Any],
    backtest: dict[str, Any],
    generated_at: str,
    llm_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    llm_settings = llm_settings or {}
    settings = {
        "provider": os.getenv(
            "LLM_PROVIDER", str(llm_settings.get("provider") or DEFAULT_PROVIDER)
        ),
        "model": os.getenv("LLM_MODEL", str(llm_settings.get("model") or DEFAULT_MODEL)),
    }
    facts = interpretation_facts(dashboard, backtest)
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_TOKEN")
    base = interpretation_base(dashboard, generated_at, settings, facts)
    if not token:
        return with_fallback(base, facts, "fallback_no_token", "HF_TOKEN ontbreekt.")
    called_at = iso_z(datetime.now(tz=UTC))
    try:
        content = call_huggingface_interpretation(token, settings["model"], facts)
        parsed = parse_llm_response(content)
        validated = validate_llm_output(parsed, facts)
        return {
            **base,
            "status": "llm_success",
            "llm_called_at_utc": called_at,
            "title": validated["title"],
            "intro": validated["intro"],
            "sections": validated["sections"],
            "warnings": [],
            "footer_note": (
                "Deze tekst is door een LLM opgesteld op basis van de exacte dashboardwaarden. "
                "De LLM bepaalt geen scores en geeft geen beleggingsadvies."
            ),
        }
    except Exception as exc:  # pragma: no cover - exact provider failures vary
        return with_fallback(base, facts, "fallback_error", str(exc), called_at)


def interpretation_base(
    dashboard: dict[str, Any],
    generated_at: str,
    settings: dict[str, str],
    facts: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_at_utc": generated_at,
        "data_cutoff_utc": dashboard["data_cutoff_utc"],
        "method_version": dashboard["method_version"],
        "provider": settings["provider"],
        "model": settings["model"],
        "llm_called_at_utc": None,
        "input_snapshot": facts,
    }


def interpretation_facts(dashboard: dict[str, Any], backtest: dict[str, Any]) -> dict[str, Any]:
    summary = dashboard.get("summary", {})
    scores = dashboard.get("scores", {})
    blocks = scores.get("blocks", {})
    current = dashboard.get("current", {})
    analog = dashboard.get("analog_summary", {})
    historical = dashboard.get("historical_context", {})
    indicator_tabs = dashboard.get("indicator_tabs", {})
    price_tab = indicator_tabs.get("price", {})
    network_tab = indicator_tabs.get("network", {})
    capital_tab = indicator_tabs.get("capital", {})
    data_audit = dashboard.get("data_audit", {})
    return {
        "regime_title": summary.get("regime_title"),
        "market_signal": score_string(scores.get("market_signal")),
        "market_signal_label": summary.get("market_signal_label"),
        "evidence_quality": score_string(scores.get("evidence_quality")),
        "evidence_label": summary.get("evidence_label"),
        "sol_price": money_string(current.get("live_sol_price") or current.get("sol_price")),
        "data_cutoff_utc": dashboard.get("data_cutoff_utc"),
        "updated_at_utc": dashboard.get("generated_at_utc"),
        "price_strength": score_string(blocks.get("price_strength")),
        "network_usage": score_string(blocks.get("network_usage")),
        "capital": score_string(blocks.get("capital")),
        "ecosystem_breadth": score_string(blocks.get("ecosystem_breadth")),
        "block_weights": {
            key: f"{round(float(value) * 100)}%"
            for key, value in (scores.get("block_weights") or {}).items()
        },
        "price_summary": price_tab.get("summary"),
        "price_components": compact_components(price_tab.get("components")),
        "network_summary": network_tab.get("summary"),
        "network_components": compact_components(network_tab.get("components")),
        "capital_summary": capital_tab.get("summary"),
        "capital_components": compact_components(capital_tab.get("components")),
        "analog_count": analog.get("count"),
        "analog_positive_frequency": pct_string(analog.get("positive_frequency")),
        "analog_median_return": pct_string(analog.get("median_return")),
        "historical_summary": historical.get("summary"),
        "backtest_7d": compact_backtest(backtest.get("7d") or {}),
        "data_quality_summary": data_audit.get("summary"),
        "data_freshness": data_audit.get("freshness", []),
        "data_warnings": data_audit.get("warnings", []),
    }


def compact_components(components: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        {
            "label": item.get("label"),
            "value": item.get("value"),
            "score": score_string(item.get("score")),
            "weight": item.get("weight"),
        }
        for item in (components or [])
    ]


def compact_backtest(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "prediction_count": row.get("prediction_count", 0),
        "directional_accuracy": pct_string(row.get("directional_accuracy")),
        "brier_skill": number_string(row.get("brier_skill")),
        "calibration_error": number_string(row.get("calibration_error")),
    }


def call_huggingface_interpretation(token: str, model: str, facts: dict[str, Any]) -> str:
    client = HttpClient(timeout=45, retries=2)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Je bent de redactionele duidingslaag van een Solana-dashboard. "
                    "Schrijf helder Nederlands voor slimme lezers zonder jargon. "
                    "Gebruik alleen de aangeleverde feiten. Geen beleggingsadvies, geen koop- "
                    "of verkoopsignalen, geen garanties. Leg termen kort uit als je ze gebruikt. "
                    "Schrijf geen redenering, geen markdown-intro en geen JSON."
                ),
            },
            {
                "role": "user",
                "content": llm_prompt(facts),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 900,
        "stream": False,
    }
    response = client.post_json(
        ROUTER_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
    )
    try:
        return str(response["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise ApiError("Onverwachte Hugging Face response") from exc


def llm_prompt(facts: dict[str, Any]) -> str:
    return (
        "Schrijf een compacte maar intelligente Nederlandse duiding voor het dashboard.\n"
        "Gebruik exact dit outputformat, inclusief de labels en blokhaken:\n\n"
        "TITEL: korte titel\n"
        "INTRO: 2 zinnen met marktsignaal en bewijskwaliteit\n"
        "[Kort beeld]\n"
        "2 tot 4 zinnen\n"
        "[Wat valt op?]\n"
        "2 tot 4 zinnen\n"
        "[Wat ondersteunt het beeld?]\n"
        "2 tot 4 zinnen\n"
        "[Wat maakt het onzeker?]\n"
        "2 tot 4 zinnen\n"
        "[Eindbeeld]\n"
        "2 tot 4 zinnen\n\n"
        "Verwerk deze exacte waarden letterlijk in de tekst: "
        f"marktsignaal {facts['market_signal']}, "
        f"bewijskwaliteit {facts['evidence_quality']}, "
        f"prijssterkte {facts['price_strength']}, "
        f"netwerkgebruik {facts['network_usage']}, "
        f"kapitaal {facts['capital']}, "
        f"ecosysteembreedte {facts['ecosystem_breadth']}.\n"
        "Gebruik daarnaast waar relevant SOL-prijs, historische vergelijking en backtestwaarden.\n"
        "Geen adviestaal, geen JSON, geen bulletlijst.\n\n"
        "Feiten:\n"
        f"{json.dumps(facts, ensure_ascii=False, sort_keys=True)}"
    )


def parse_llm_response(content: str) -> dict[str, Any]:
    try:
        return parse_json_object(content)
    except Exception:
        return parse_marked_text(content)


def parse_json_object(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("LLM-output is geen JSON-object")
    return parsed


def parse_marked_text(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    title = match_line(cleaned, "TITEL")
    intro = match_line(cleaned, "INTRO")
    if not title or not intro:
        raise ValueError("LLM-output mist TITEL of INTRO")
    sections = []
    for index, heading in enumerate(FIXED_HEADINGS):
        next_heading = FIXED_HEADINGS[index + 1] if index + 1 < len(FIXED_HEADINGS) else None
        text = extract_marked_section(cleaned, heading, next_heading)
        if not text:
            raise ValueError(f"LLM-output mist sectie: {heading}")
        sections.append({"heading": heading, "text": text})
    return {"title": title, "intro": intro, "sections": sections}


def match_line(content: str, label: str) -> str:
    match = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", content)
    return clean_text(match.group(1)) if match else ""


def extract_marked_section(content: str, heading: str, next_heading: str | None) -> str:
    start_patterns = [
        rf"^\s*\[{re.escape(heading)}\]\s*$",
        rf"^\s*#+\s*{re.escape(heading)}\s*$",
    ]
    start_match = None
    for pattern in start_patterns:
        start_match = re.search(pattern, content, flags=re.IGNORECASE | re.MULTILINE)
        if start_match:
            break
    if not start_match:
        return ""
    start = start_match.end()
    end = len(content)
    if next_heading:
        end_patterns = [
            rf"^\s*\[{re.escape(next_heading)}\]\s*$",
            rf"^\s*#+\s*{re.escape(next_heading)}\s*$",
        ]
        for pattern in end_patterns:
            end_match = re.search(pattern, content[start:], flags=re.IGNORECASE | re.MULTILINE)
            if end_match:
                end = start + end_match.start()
                break
    return clean_text(content[start:end])


def validate_llm_output(data: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    title = clean_text(data.get("title"))
    intro = clean_text(data.get("intro"))
    sections = data.get("sections")
    if not title or not intro or not isinstance(sections, list):
        raise ValueError("LLM-output mist titel, intro of secties")
    normalized_sections = []
    for expected, section in zip(FIXED_HEADINGS, sections, strict=False):
        if not isinstance(section, dict):
            raise ValueError("Sectie is geen object")
        heading = clean_text(section.get("heading"))
        text = clean_text(section.get("text"))
        if heading != expected or not text:
            raise ValueError("LLM-output gebruikt niet de vaste koppen")
        normalized_sections.append({"heading": heading, "text": text})
    if [section["heading"] for section in normalized_sections] != FIXED_HEADINGS:
        raise ValueError("LLM-output bevat niet alle vaste koppen")
    joined = " ".join([title, intro, *(section["text"] for section in normalized_sections)]).lower()
    if any(term in joined for term in FORBIDDEN_TERMS):
        raise ValueError("LLM-output bevat verboden adviestaal")
    required_values = [
        facts["market_signal"],
        facts["evidence_quality"],
        facts["price_strength"],
        facts["network_usage"],
        facts["capital"],
        facts["ecosystem_breadth"],
    ]
    missing = [value for value in required_values if value and value not in joined]
    if missing:
        raise ValueError(f"LLM-output mist dashboardwaarden: {missing}")
    return {"title": title, "intro": intro, "sections": normalized_sections}


def with_fallback(
    base: dict[str, Any],
    facts: dict[str, Any],
    status: str,
    warning: str,
    called_at: str | None = None,
) -> dict[str, Any]:
    return {
        **base,
        "status": status,
        "llm_called_at_utc": called_at,
        "title": fallback_title(facts),
        "intro": (
            f"Het marktsignaal staat op {facts['market_signal']} ({facts['market_signal_label']}) "
            f"en de bewijskwaliteit op {facts['evidence_quality']} ({facts['evidence_label']}). "
            f"Deze duiding gebruikt de dashboardwaarden tot {facts['data_cutoff_utc']}."
        ),
        "sections": fallback_sections(facts),
        "warnings": [warning],
        "footer_note": (
            "Fallbacktekst: automatisch opgesteld uit vaste regels omdat de LLM-call niet "
            "beschikbaar of niet geldig was. Dit is geen beleggingsadvies."
        ),
    }


def fallback_title(facts: dict[str, Any]) -> str:
    return facts.get("regime_title") or "Duiding van het actuele beeld"


def fallback_sections(facts: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "heading": "Kort beeld",
            "text": (
                f"SOL staat rond {facts['sol_price']}. Het dashboard geeft een marktsignaal "
                f"van {facts['market_signal']} en een bewijskwaliteit van "
                f"{facts['evidence_quality']}. Dat betekent dat het beeld bruikbaar is, maar "
                "dat de score altijd samen met de onderliggende blokken gelezen moet worden."
            ),
        },
        {
            "heading": "Wat valt op?",
            "text": (
                f"Prijssterkte staat op {facts['price_strength']}, netwerkgebruik op "
                f"{facts['network_usage']}, kapitaal op {facts['capital']} en "
                f"ecosysteembreedte op {facts['ecosystem_breadth']}. De kern is dus de "
                "verhouding tussen koersgedrag, netwerkactiviteit, kapitaalstromen en de "
                "breedte van het Solana-ecosysteem."
            ),
        },
        {
            "heading": "Wat ondersteunt het beeld?",
            "text": (
                f"De historische vergelijking gebruikt {facts['analog_count']} vergelijkbare "
                f"dagen. Daarvan was {facts['analog_positive_frequency']} positief na de "
                f"gekozen horizon, met een mediaan rendement van "
                f"{facts['analog_median_return']}. De 7-daagse backtest bevat "
                f"{facts['backtest_7d']['prediction_count']} voorspellingen."
            ),
        },
        {
            "heading": "Wat maakt het onzeker?",
            "text": (
                f"De bewijskwaliteit is {facts['evidence_quality']}, dus de methode zegt niet "
                "dat de uitkomst zeker is. Backtestwaarden zoals Brier skill "
                f"({facts['backtest_7d']['brier_skill']}) en kalibratiefout "
                f"({facts['backtest_7d']['calibration_error']}) laten zien hoe goed eerdere "
                "signalen werkten buiten de data waarop ze zijn gevormd."
            ),
        },
        {
            "heading": "Eindbeeld",
            "text": (
                f"De dashboardlezing is: {facts['regime_title']}. Met marktsignaal "
                f"{facts['market_signal']} en bewijskwaliteit {facts['evidence_quality']} is "
                "dit een gestructureerde duiding van de data, geen voorspelling met zekerheid "
                "en geen financieel advies."
            ),
        },
    ]


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def score_string(value: Any) -> str:
    if value is None:
        return "n.v.t."
    return f"{round(float(value))}/100"


def pct_string(value: Any) -> str:
    if value is None:
        return "n.v.t."
    return f"{float(value) * 100:.1f}%"


def number_string(value: Any) -> str:
    if value is None:
        return "n.v.t."
    return f"{float(value):.3f}"


def money_string(value: Any) -> str:
    if value is None:
        return "n.v.t."
    return f"${float(value):.2f}"
