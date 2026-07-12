from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "site/index.html").read_text(encoding="utf-8")
for tab in [
    "Actueel",
    "Prijs",
    "Netwerk",
    "Kapitaal",
    "Voorspellingskracht",
    "Bewijs",
    "Ecosysteem",
    "Historische vergelijking",
    "Datakwaliteit",
    "Backtest",
    "Trackrecord",
    "Methode",
    "Data & logboek",
    "Signaalonderzoek",
    "Lead-lag tabel",
]:
    if tab not in html:
        raise SystemExit(f"Missing tab: {tab}")
print("Smoke test OK")
