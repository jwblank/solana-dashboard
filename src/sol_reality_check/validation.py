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
    for filename, schema_name in SCHEMA_MAP.items():
        data_path = data_dir / filename
        if not data_path.exists():
            raise FileNotFoundError(data_path)
        data = json.loads(data_path.read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
        validate(data, schema)
    for path in data_dir.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        if "NaN" in text or "Infinity" in text:
            raise ValueError(f"Invalid numeric token in {path}")
