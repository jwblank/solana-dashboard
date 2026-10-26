from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = [
    "index.html",
    "app.js",
    "styles.css",
    "build-version.js",
    "data/dashboard.json",
    "data/overview.json",
    "data/overview_history.json",
    "data/ledger.json",
    "data/backtest_summary.json",
    "data/signaalonderzoek.json",
    "data/predictive_power.json",
    "data/predictive_monitor.json",
    "data/signal_definitions.jsonl",
    "data/signal_events.jsonl",
    "data/signal_outcomes.jsonl",
]
missing = [item for item in required if not (ROOT / "site" / item).exists()]
if missing:
    raise SystemExit(f"Missing site files: {missing}")
print("Site build OK")
