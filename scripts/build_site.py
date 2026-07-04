from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = ["index.html", "app.js", "styles.css", "data/dashboard.json"]
missing = [item for item in required if not (ROOT / "site" / item).exists()]
if missing:
    raise SystemExit(f"Missing site files: {missing}")
print("Site build OK")
