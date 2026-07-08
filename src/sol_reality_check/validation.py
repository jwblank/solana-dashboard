from __future__ import annotations

import json

from jsonschema import validate

from sol_reality_check.config import ROOT

SCHEMA_MAP = {
    "dashboard.json": "dashboard.schema.json",
    "backtest_summary.json": "backtest.schema.json",
    "source_status.json": "source_status.schema.json",
}


def validate_outputs() -> None:
    data_dir = ROOT / "site" / "data"
    loaded: dict[str, dict] = {}
    for filename, schema_name in SCHEMA_MAP.items():
        data_path = data_dir / filename
        if not data_path.exists():
            raise FileNotFoundError(data_path)
        data = json.loads(data_path.read_text(encoding="utf-8"))
        loaded[filename] = data
        schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
        validate(data, schema)
    for path in data_dir.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        if "NaN" in text or "Infinity" in text:
            raise ValueError(f"Invalid numeric token in {path}")
    validate_signal_research(data_dir, loaded.get("dashboard.json", {}))


def validate_signal_research(data_dir, dashboard: dict) -> None:
    path = data_dir / "signaalonderzoek.json"
    if not path.exists():
        return
    research = json.loads(path.read_text(encoding="utf-8"))
    rows = research.get("rows", [])
    if dashboard.get("mode") != "production":
        return
    bad_rows = [row for row in rows if row.get("mode") != "production"]
    if bad_rows:
        raise ValueError("Production signaalonderzoek contains non-production rows")
    if not rows:
        raise ValueError("Production signaalonderzoek contains no rows")
    latest = rows[-1]
    if latest.get("run_at_utc") != dashboard.get("generated_at_utc"):
        raise ValueError("Latest signaalonderzoek row does not match dashboard update time")
    current = dashboard.get("current", {})
    if latest.get("sol_price") != current.get("sol_price"):
        raise ValueError("Latest signaalonderzoek SOL price does not match dashboard")
    if latest.get("btc_price") != current.get("btc_price"):
        raise ValueError("Latest signaalonderzoek BTC price does not match dashboard")
