import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = [
    "index.html",
    "app.js",
    "research.js",
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
    "data/research_monitor.json",
    "data/research_baseline_manifest.json",
    "data/research_baseline.tar.gz",
    "data/signal_definitions.jsonl",
    "data/signal_events.jsonl",
    "data/signal_outcomes.jsonl",
]
missing = [item for item in required if not (ROOT / "site" / item).exists()]
if missing:
    raise SystemExit(f"Missing site files: {missing}")
print("Site build OK")

# Compile from the reviewed snapshot on every deployment, including daily updates.
# The original datasets and original dashboard remain independently accessible.
snapshot = ROOT / "site/data/lab_snapshot.json"
if not snapshot.exists():
    raise SystemExit("Missing reviewed lab snapshot; run scripts/export_lab_snapshot.py")
shutil.copyfile(snapshot, ROOT / "web/src/data.json")
build_env = {
    k: v for k, v in os.environ.items() if k not in {"CODEX_SESSION_ID", "CODEX_THREAD_ID"}
}
subprocess.run(["pnpm", "run", "build"], cwd=ROOT / "web", env=build_env, check=True)
shutil.copyfile(ROOT / "web/dist/index.html", ROOT / "site/index.html")
print("Research dashboard compiled from the preserved history")
