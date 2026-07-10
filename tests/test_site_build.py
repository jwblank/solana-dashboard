import json
from pathlib import Path

from sol_reality_check.pipeline import build_outputs


def test_site_contains_required_tabs(monkeypatch):
    monkeypatch.setenv("APP_MODE", "demo")
    build_outputs("demo")
    html = Path("site/index.html").read_text(encoding="utf-8")
    required_text = [
        "Overzicht",
        "Duiding",
        "Vandaag",
        "Prijs",
        "Gebruik & ecosysteem",
        "Kapitaalstromen",
        "Signaalonderzoek",
        "Onderbouwing",
        "Historische toets",
        "Open logboek",
        "Zo werkt het",
    ]
    for text in required_text:
        assert text in html
    assert '<section id="overview" class="panel active">' in html
    assert "/data/dashboard.json" not in html


def test_interpretation_archive_is_published(monkeypatch):
    monkeypatch.setenv("APP_MODE", "demo")
    build_outputs("demo")
    latest = json.loads(Path("site/data/interpretation.json").read_text(encoding="utf-8"))
    index = json.loads(Path("site/data/interpretations/index.json").read_text(encoding="utf-8"))
    assert index["entries"]
    day_path = Path("site/data/interpretations") / f"{latest['interpretation_date']}.json"
    archived = json.loads(day_path.read_text(encoding="utf-8"))
    assert archived["date"] == latest["interpretation_date"]
    assert archived["analysis_text"]
