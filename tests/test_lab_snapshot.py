import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from sol_reality_check.lab_snapshot import build_lab_snapshot, epoch
from sol_reality_check.research_note import research_note


@pytest.fixture(scope="module")
def lab():
    # Real production fixture is read only. Demo tests may have rewritten the
    # derived dashboard; retain the committed reviewed snapshot for those runs.
    root = Path(__file__).resolve().parents[1]
    dashboard = json.loads((root / "site/data/dashboard.json").read_text())
    if dashboard["mode"] != "production":
        return json.loads((root / "site/data/lab_snapshot.json").read_text())
    primary = [
        *root.glob("data/curated/*.parquet"),
        *root.glob("data/ledger/*.jsonl"),
        *root.glob("data/research/*.jsonl"),
    ]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in primary}
    snapshot = build_lab_snapshot(root)
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in primary}
    return snapshot


def test_price_and_signal_have_their_own_real_timestamps(lab):
    rows = lab["queries"]["history"]["rows"]
    assert len(rows) >= 129
    assert len({r["date"] for r in rows}) == len(rows)
    for row in rows:
        assert row["close_time"] == epoch(row["date"] + "T23:59:59Z")
        assert row["published_time"] == epoch(row["published_at"])
        assert row["price_method"]


def test_forecast_marks_never_backdate_prospective_registration(lab):
    rows = lab["queries"]["forecasts"]["rows"]
    assert {r["phase"] for r in rows} == {"reconstructed", "prospective"}
    for row in rows:
        assert row["mark_time"] == epoch(row["mark_at"])
        if row["phase"] == "prospective":
            assert pd.Timestamp(row["mark_at"]) < pd.Timestamp(row["entry_date"] + "T23:59:59Z")
        assert (
            row["correct"] is None
            if row["sol_return"] is None or not row["model_available"]
            else isinstance(row["correct"], bool)
        )
    # Keep misses, up and down forecasts; a chart must not select only successes.
    scored = [r for r in rows if r["correct"] is not None]
    assert {r["correct"] for r in scored} == {True, False}
    assert {r["predicted_direction"] for r in scored} == {"up", "down"}


def test_llm_cannot_invent_evidence(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "test-not-a-real-token")
    monkeypatch.setattr(
        "sol_reality_check.research_note.HttpClient.post_json",
        lambda *a, **k: {"choices": [{"message": {"content": "SOL stijgt gegarandeerd 50%"}}]},
    )
    result = research_note({"records": [], "generated_at_utc": "2026-11-11T00:00:00Z"})
    assert result["status"] == "fixed_wording_provider_unavailable"
    assert "50%" not in result["text"]
    assert "nog geen extra voorspelkracht" in result["text"]
