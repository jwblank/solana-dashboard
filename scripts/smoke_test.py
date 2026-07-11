from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "site/index.html").read_text(encoding="utf-8")
for tab in [
    "Actueel",
    "Analyse",
    "Bewijs",
    "Totaalbeeld",
    "Prijs",
    "Netwerk",
    "Kapitaal",
    "Ecosysteem",
    "Historie",
    "Kwaliteit",
    "Backtest",
    "Trackrecord",
    "Methode",
    "Data & logboek",
    "Signaalonderzoek",
]:
    if tab not in html:
        raise SystemExit(f"Missing tab: {tab}")
print("Smoke test OK")
