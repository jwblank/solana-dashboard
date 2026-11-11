"""LLM wording selection; the evidence status and every offered sentence are code-owned."""

from __future__ import annotations

import os
from typing import Any

from sol_reality_check.clients import HttpClient
from sol_reality_check.llm_interpretation import DEFAULT_MODEL, ROUTER_URL


def research_note(monitor: dict[str, Any]) -> dict[str, Any]:
    completed = any(
        r.get("phase") == "prospective" and r.get("sol_return") is not None
        for r in monitor["records"]
        if r.get("horizon_days") == 7
    )
    variants = (
        [
            "De nieuwe meetvensters lopen nog. De historische patronen geven aanleiding tot "
            "onderzoek, maar bevestigen nog geen extra voorspelkracht.",
            "De kandidaten zijn vooraf vastgelegd. Eerst moeten de nieuwe meetvensters "
            "aflopen; pas daarna kan hun extra voorspelkracht worden beoordeeld.",
        ]
        if not completed
        else [
            "Er zijn nieuwe uitkomsten beschikbaar. Beoordeel de meerwaarde tegenover de "
            "koersbasis samen met de onzekerheidsmarge en de aantallen per richting.",
            "De nieuwe toets bevat afgeronde meetvensters. Een positief gemiddeld verschil "
            "is pas overtuigender wanneer de onzekerheidsmarge en herhaalde metingen dat steunen.",
        ]
    )
    result = {
        "generated_at": monitor["generated_at_utc"],
        "text": variants[0],
        "status": "fixed_wording",
        "model": None,
        "policy": "LLM kiest uitsluitend een vooraf gecontroleerde formulering; geen eigen claims.",
    }
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_TOKEN")
    if not token:
        return result
    model = os.getenv("LLM_MODEL", DEFAULT_MODEL)
    try:
        response = HttpClient(timeout=20, retries=1).post_json(
            ROUTER_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Kies de helderste Nederlandse formulering voor een compact openbaar "
                            "statistisch onderzoek naar Solana. Antwoord uitsluitend 0 of 1.\n"
                            + "\n".join(f"{i}: {text}" for i, text in enumerate(variants))
                        ),
                    }
                ],
                "temperature": 0,
                "max_tokens": 5,
            },
        )
        choice = str(response["choices"][0]["message"]["content"]).strip()
        if choice not in {"0", "1"}:
            raise ValueError("Ongeldige formuleringkeuze")
        result.update(text=variants[int(choice)], status="llm_success", model=model)
    except Exception:
        # No provider payloads or credentials in public output; a failure cannot stop collection.
        result["status"] = "fixed_wording_provider_unavailable"
    return result
