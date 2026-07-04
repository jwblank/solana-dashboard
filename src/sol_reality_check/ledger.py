from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sol_reality_check.utils import payload_hash


def with_hash(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    data["payload_sha256"] = payload_hash(data)
    return data


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def append_unique(path: Path, payload: dict[str, Any], key_fields: list[str]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_jsonl(path)
    key = tuple(payload[field] for field in key_fields)
    if any(tuple(row[field] for field in key_fields) == key for row in existing):
        return False
    row = with_hash(payload)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        )
    return True


def check_ledger(predictions_path: Path, outcomes_path: Path) -> list[str]:
    errors: list[str] = []
    predictions = read_jsonl(predictions_path)
    outcomes = read_jsonl(outcomes_path)
    ids = set()
    for row in predictions:
        pid = row.get("prediction_id")
        if pid in ids:
            errors.append(f"Duplicate prediction_id: {pid}")
        ids.add(pid)
        if payload_hash(row) != row.get("payload_sha256"):
            errors.append(f"Invalid prediction hash: {pid}")
    outcome_keys = set()
    for row in outcomes:
        key = (row.get("prediction_id"), row.get("horizon"))
        if key in outcome_keys:
            errors.append(f"Duplicate outcome: {key}")
        outcome_keys.add(key)
        if row.get("prediction_id") not in ids:
            errors.append(f"Outcome without prediction: {key}")
        if payload_hash(row) != row.get("payload_sha256"):
            errors.append(f"Invalid outcome hash: {key}")
    return errors
