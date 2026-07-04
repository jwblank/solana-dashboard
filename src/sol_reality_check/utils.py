from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(tz=UTC).replace(microsecond=0)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def payload_hash(data: dict[str, Any]) -> str:
    payload = {k: v for k, v in data.items() if k != "payload_sha256"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def write_json(path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
