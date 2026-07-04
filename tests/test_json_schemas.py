import json

from jsonschema import validate

from sol_reality_check.config import ROOT
from sol_reality_check.pipeline import build_outputs


def test_dashboard_schema_validation(monkeypatch):
    monkeypatch.setenv("APP_MODE", "demo")
    build_outputs("demo")
    data = json.loads((ROOT / "site/data/dashboard.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/dashboard.schema.json").read_text(encoding="utf-8"))
    validate(data, schema)
