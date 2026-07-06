from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import Any

from sol_reality_check.clients import ApiError, HttpClient
from sol_reality_check.utils import iso_z

DEFAULT_PROVIDER = "Hugging Face Inference Providers"
DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
LEGACY_HEADINGS = [
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
        parsed = parse_llm_response(content, facts)
        completed, completion_warnings = complete_required_values(parsed, facts)
        validated = validate_llm_output(completed, facts)
        return {
            **base,
            "status": "llm_success",
            "llm_called_at_utc": called_at,
            "title": validated["title"],
            "intro": validated["intro"],
            "analysis_text": validated["analysis_text"],
            "warnings": completion_warnings,
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
        "interpretation_date": str(dashboard["data_cutoff_utc"])[:10],
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
                    "Vermijd herhaling. Beschrijf niet alleen cijfers, maar duid de spanning "
                    "tussen prijs, netwerk, kapitaal, ecosysteembreedte en bewijskwaliteit. "
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
    frame = interpretation_frame(facts)
    return (
        "Schrijf één compacte, volledige Nederlandse analyse voor het dashboard.\n"
        "Gebruik exact dit outputformat:\n\n"
        "TITEL: korte titel\n"
        "ANALYSE:\n"
        "Kernbeeld: 2 korte zinnen\n"
        "Spanning in de data: 2 tot 3 korte zinnen\n"
        "Bewijskracht: 2 korte zinnen\n"
        "Waarop letten: 1 tot 2 korte zinnen\n"
        "Eindbeeld: 1 scherpe slotzin\n\n"
        f"Interpretatiekader: {frame}.\n"
        "Gebruik de vijf kopjes exact zoals hierboven. Schrijf onder elk kopje gewone zinnen, "
        "geen bullets. Gebruik eenvoudige maar scherpe taal.\n"
        "Verwerk deze exacte waarden letterlijk in de tekst: "
        f"marktsignaal {facts['market_signal']}, "
        f"bewijskwaliteit {facts['evidence_quality']}, "
        f"prijssterkte {facts['price_strength']}, "
        f"netwerkgebruik {facts['network_usage']}, "
        f"kapitaal {facts['capital']}, "
        f"ecosysteembreedte {facts['ecosystem_breadth']}.\n"
        "Gebruik daarnaast waar relevant SOL-prijs, historische vergelijking en backtestwaarden. "
        "Leg kort uit wat bewijskwaliteit betekent als je die term gebruikt. "
        "Geen adviestaal, geen JSON, geen bulletlijst, geen herhaling.\n\n"
        "Feiten:\n"
        f"{json.dumps(facts, ensure_ascii=False, sort_keys=True)}"
    )


def interpretation_frame(facts: dict[str, Any]) -> str:
    price = score_value(facts.get("price_strength"))
    network = score_value(facts.get("network_usage"))
    capital = score_value(facts.get("capital"))
    breadth = score_value(facts.get("ecosystem_breadth"))
    evidence = score_value(facts.get("evidence_quality"))
    if price >= 60 and network >= 60 and capital >= 60:
        return "breed bevestigd; prijs, netwerk en kapitaal wijzen dezelfde kant op"
    if price >= 60 and (network < 60 or capital < 60):
        return "koers loopt vooruit; prijs is sterker dan de onderliggende bevestiging"
    if price < 55 and (network >= 60 or capital >= 60 or breadth >= 65):
        return "onderliggende kracht zonder volledige koersbevestiging"
    if evidence < 60:
        return "positief of gemengd signaal met beperkte bewijskracht"
    return "gemengd beeld; de blokken spreken elkaar deels tegen"


def parse_llm_response(content: str, facts: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return parse_json_object(content)
    except Exception:
        return parse_marked_text(content, facts)


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


def parse_marked_text(content: str, facts: dict[str, Any] | None = None) -> dict[str, Any]:
    cleaned = content.strip()
    title = match_line(cleaned, "TITEL")
    intro = match_line(cleaned, "INTRO")
    analysis = match_block(cleaned, "ANALYSE")
    if not analysis:
        sections = []
        first_heading_start = len(cleaned)
        for index, heading in enumerate(LEGACY_HEADINGS):
            next_heading = LEGACY_HEADINGS[index + 1] if index + 1 < len(LEGACY_HEADINGS) else None
            text, section_start = extract_marked_section(cleaned, heading, next_heading)
            first_heading_start = min(first_heading_start, section_start)
            if text:
                sections.append(text)
        analysis = " ".join(sections) if sections else infer_analysis(cleaned)
    else:
        first_heading_start = cleaned.upper().find("ANALYSE")
    title = title or infer_title(cleaned, facts)
    intro = intro or infer_intro(cleaned, first_heading_start, facts)
    return {"title": title, "intro": intro, "analysis_text": analysis}


def match_line(content: str, label: str) -> str:
    match = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", content)
    return clean_text(match.group(1)) if match else ""


def match_block(content: str, label: str) -> str:
    match = re.search(
        rf"(?ims)^\s*{re.escape(label)}\s*:\s*(.+?)(?:\n\s*[A-ZÀ-Ý][A-ZÀ-Ý _-]{{2,}}\s*:|\Z)",
        content,
    )
    return clean_text(match.group(1)) if match else ""


def extract_marked_section(
    content: str, heading: str, next_heading: str | None
) -> tuple[str, int]:
    start_patterns = [
        rf"^\s*\[{re.escape(heading)}\]\s*$",
        rf"^\s*#+\s*{re.escape(heading)}\s*:?\s*$",
        rf"^\s*\*{{0,2}}{re.escape(heading)}\*{{0,2}}\s*:?\s*$",
        rf"^\s*\d+[.)]\s*\*{{0,2}}{re.escape(heading)}\*{{0,2}}\s*:?\s*$",
    ]
    start_match = None
    for pattern in start_patterns:
        start_match = re.search(pattern, content, flags=re.IGNORECASE | re.MULTILINE)
        if start_match:
            break
    if not start_match:
        return "", len(content)
    start = start_match.end()
    end = len(content)
    if next_heading:
        end_patterns = [
            rf"^\s*\[{re.escape(next_heading)}\]\s*$",
            rf"^\s*#+\s*{re.escape(next_heading)}\s*:?\s*$",
            rf"^\s*\*{{0,2}}{re.escape(next_heading)}\*{{0,2}}\s*:?\s*$",
            rf"^\s*\d+[.)]\s*\*{{0,2}}{re.escape(next_heading)}\*{{0,2}}\s*:?\s*$",
        ]
        for pattern in end_patterns:
            end_match = re.search(pattern, content[start:], flags=re.IGNORECASE | re.MULTILINE)
            if end_match:
                end = start + end_match.start()
                break
    return clean_text(content[start:end]), start_match.start()


def infer_title(content: str, facts: dict[str, Any] | None) -> str:
    if facts and facts.get("regime_title"):
        return clean_text(facts["regime_title"])
    for line in content.splitlines():
        text = clean_text(line.strip("#* []:"))
        if text and text not in LEGACY_HEADINGS and not text.upper().startswith("ANALYSE"):
            return text[:90]
    return "Kwalitatieve duiding"


def infer_intro(content: str, first_heading_start: int, facts: dict[str, Any] | None) -> str:
    preamble = clean_text(
        re.sub(r"(?im)^\s*TITEL\s*:\s*.+?$", "", content[:first_heading_start]).strip()
    )
    preamble = re.sub(r"(?im)^\s*INTRO\s*:\s*", "", preamble).strip()
    if preamble:
        return preamble[:360]
    if facts:
        return (
            f"Het marktsignaal staat op {facts['market_signal']} "
            f"({facts['market_signal_label']}) en de bewijskwaliteit op "
            f"{facts['evidence_quality']} ({facts['evidence_label']}). Deze duiding gebruikt "
            f"de dashboardwaarden tot {facts['data_cutoff_utc']}."
        )
    return "Deze duiding gebruikt de dashboardwaarden en leest de indicatoren in samenhang."


def infer_analysis(content: str) -> str:
    cleaned = re.sub(r"(?im)^\s*TITEL\s*:\s*.+?$", "", content)
    cleaned = re.sub(r"(?im)^\s*INTRO\s*:\s*.+?$", "", cleaned)
    return clean_text(cleaned)


def validate_llm_output(data: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    title = clean_text(data.get("title"))
    intro = clean_text(data.get("intro"))
    analysis = clean_text(data.get("analysis_text") or legacy_sections_to_text(data))
    if not title or not intro or not analysis:
        raise ValueError("LLM-output mist titel, intro of analyse")
    joined = " ".join([title, intro, analysis]).lower()
    if any(term in joined for term in FORBIDDEN_TERMS):
        raise ValueError("LLM-output bevat verboden adviestaal")
    required_values = [value for _, value in required_dashboard_values(facts)]
    missing = [value for value in required_values if value and value not in joined]
    if missing:
        raise ValueError(f"LLM-output mist dashboardwaarden: {missing}")
    return {"title": title, "intro": intro, "analysis_text": analysis}


def complete_required_values(
    data: dict[str, Any], facts: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    values = required_dashboard_values(facts)
    joined = output_text(data).lower()
    missing = [(label, value) for label, value in values if value and value.lower() not in joined]
    if not missing:
        return data, []
    summary = "Voor de controleerbaarheid staan de kernwaarden expliciet in beeld: " + ", ".join(
        f"{label} {value}" for label, value in values if value
    ) + "."
    existing_analysis = data.get("analysis_text") or legacy_sections_to_text(data)
    return {
        **data,
        "analysis_text": clean_text(f"{existing_analysis} {summary}"),
    }, [
        "LLM-output aangevuld met verplichte dashboardwaarden: "
        + ", ".join(value for _, value in missing)
        + "."
    ]


def required_dashboard_values(facts: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        ("marktsignaal", facts["market_signal"]),
        ("bewijskwaliteit", facts["evidence_quality"]),
        ("prijssterkte", facts["price_strength"]),
        ("netwerkgebruik", facts["network_usage"]),
        ("kapitaal", facts["capital"]),
        ("ecosysteembreedte", facts["ecosystem_breadth"]),
    ]


def output_text(data: dict[str, Any]) -> str:
    return " ".join(
        [
            clean_text(data.get("title")),
            clean_text(data.get("intro")),
            clean_text(data.get("analysis_text")),
            legacy_sections_to_text(data),
        ]
    )


def legacy_sections_to_text(data: dict[str, Any]) -> str:
    raw_sections = data.get("sections")
    sections: list[Any] = raw_sections if isinstance(raw_sections, list) else []
    return clean_text(
        " ".join(
            clean_text(section.get("text")) for section in sections if isinstance(section, dict)
        )
    )


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
        "analysis_text": fallback_analysis(facts),
        "warnings": [warning],
        "footer_note": (
            "Fallbacktekst: automatisch opgesteld uit vaste regels omdat de LLM-call niet "
            "beschikbaar of niet geldig was. Dit is geen beleggingsadvies."
        ),
    }


def fallback_title(facts: dict[str, Any]) -> str:
    return facts.get("regime_title") or "Duiding van het actuele beeld"


def fallback_analysis(facts: dict[str, Any]) -> str:
    return (
        "Kernbeeld: "
        f"SOL staat rond {facts['sol_price']} en het dashboard geeft een marktsignaal van "
        f"{facts['market_signal']}. De dashboardlezing is: {facts['regime_title']}.\n\n"
        "Spanning in de data: "
        f"De belangrijkste verhouding zit tussen prijssterkte {facts['price_strength']}, "
        f"netwerkgebruik {facts['network_usage']}, kapitaal {facts['capital']} en "
        f"ecosysteembreedte {facts['ecosystem_breadth']}. Als prijs sterker is dan netwerk en "
        "kapitaal, loopt de markt mogelijk vooruit op bredere bevestiging; als netwerk en "
        "kapitaal meebewegen, wordt het beeld steviger.\n\n"
        "Bewijskracht: "
        f"De bewijskwaliteit is {facts['evidence_quality']}. Bewijskwaliteit betekent hoe "
        "stevig de actuele conclusie historisch en datatechnisch onderbouwd is; bij beperkt "
        "bewijs moet het signaal voorzichtig gelezen worden.\n\n"
        "Waarop letten: "
        f"De historische vergelijking gebruikt {facts['analog_count']} vergelijkbare dagen; "
        f"daarvan was {facts['analog_positive_frequency']} positief, met een mediaan rendement "
        f"van {facts['analog_median_return']}.\n\n"
        "Eindbeeld: "
        "Dit is een gestructureerde dataduiding van de actuele Solana-context, geen financieel "
        "advies."
    )


def score_value(value: Any) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return float(match.group(0)) if match else 0.0


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
