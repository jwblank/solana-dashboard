from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: str) -> dict[str, Any]:
    with (ROOT / path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


def settings() -> dict[str, Any]:
    data = load_yaml("config/settings.yml")
    required = ["project", "history", "analogs", "backtest", "publication"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"Missing settings sections: {missing}")
    return data


def indicators() -> dict[str, Any]:
    data = load_yaml("config/indicators.yml")
    if "blocks" not in data or "validated_market_signal" not in data:
        raise ValueError("Indicator configuration misses scoring weights")
    return data
