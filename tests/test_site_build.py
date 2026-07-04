from pathlib import Path

from sol_reality_check.pipeline import build_outputs


def test_site_contains_required_tabs(monkeypatch):
    monkeypatch.setenv("APP_MODE", "demo")
    build_outputs("demo")
    html = Path("site/index.html").read_text(encoding="utf-8")
    for text in ["Vandaag", "Bewijs", "Backtest", "Open logboek", "Zo werkt het"]:
        assert text in html
    assert "/data/dashboard.json" not in html
