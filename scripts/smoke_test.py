from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "site/index.html").read_text(encoding="utf-8")
for tab in ["Vandaag", "Prijs", "Netwerk & ecosysteem", "Kapitaal", "Duiding", "Bewijs"]:
    if tab not in html:
        raise SystemExit(f"Missing tab: {tab}")
print("Smoke test OK")
