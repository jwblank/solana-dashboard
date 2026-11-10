"""Lossless baseline and content-addressed, immutable inputs for research runs."""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path
from typing import Any

import pandas as pd

from sol_reality_check.predictive_monitor import append_immutable
from sol_reality_check.utils import canonical_json, iso_z, utc_now, write_json


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_create(path: Path, content: bytes) -> None:
    """Never replace an archive; a conflicting existing file stops the update."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Archive conflict: {path.name}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def ensure_baseline(root: Path) -> dict[str, Any]:
    directory = root / "data/research/baseline"
    manifest_path = directory / "manifest.json"
    archive_path = directory / "collected-data.tar.gz"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        verify_baseline(root, manifest)
        return manifest
    if archive_path.exists():
        raise ValueError("Baseline archive exists without its manifest; refusing replacement")
    paths = sorted(
        {
            p
            for base in [root / "data/curated", root / "data/ledger", root / "site/data"]
            if base.exists()
            for p in base.rglob("*")
            if p.is_file()
        }
    )
    contents = {str(p.relative_to(root)): p.read_bytes() for p in paths}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, content in contents.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o644
            info.mtime = 0
            tar.addfile(info, io.BytesIO(content))
    compressed = gzip.compress(buffer.getvalue(), mtime=0)
    manifest = {
        "schema_version": "1.0",
        "created_at_utc": iso_z(utc_now()),
        "archive_sha256": sha256(compressed),
        "file_count": len(contents),
        "files": {name: {"sha256": sha256(b), "bytes": len(b)} for name, b in contents.items()},
        "policy": "Oorspronkelijke bytes, inclusief alle dubbele runs en oude uitkomsten.",
    }
    atomic_create(archive_path, compressed)
    write_json(manifest_path, manifest)
    verify_baseline(root, manifest)
    return manifest


def verify_baseline(
    root: Path, manifest: dict[str, Any] | None = None, directory: Path | None = None
) -> None:
    directory = directory or root / "data/research/baseline"
    if manifest is None:
        manifest = json.loads((directory / "manifest.json").read_text())
    content = (directory / "collected-data.tar.gz").read_bytes()
    if sha256(content) != manifest["archive_sha256"]:
        raise ValueError("Baseline archive hash mismatch")
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
        members = {member.name: member for member in tar.getmembers()}
        if set(members) != set(manifest["files"]):
            raise ValueError("Baseline archive file inventory differs")
        for name, metadata in manifest["files"].items():
            handle = tar.extractfile(members[name])
            if handle is None or sha256(handle.read()) != metadata["sha256"]:
                raise ValueError(f"Baseline file hash mismatch: {name}")


def archive_run(
    root: Path,
    dashboard: dict[str, Any],
    history: pd.DataFrame,
    source_status: dict[str, Any],
    settings: dict[str, Any],
    indicators: dict[str, Any],
) -> None:
    """Archive actual model inputs, not credentials or an invented raw API response."""
    # Parquet preserves full float precision, missingness, column types and timestamps.
    buffer = io.BytesIO()
    history.to_parquet(buffer, index=True)
    research_path = root / "data/curated/signaalonderzoek.parquet"
    snapshot = {
        "schema_version": "1.1",
        "run_at_utc": dashboard["generated_at_utc"],
        "data_cutoff_utc": dashboard["data_cutoff_utc"],
        "dashboard": dashboard,
        "history": {
            "format": "parquet-base64",
            "row_count": len(history),
            "sha256": sha256(buffer.getvalue()),
            "bytes_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        },
        "research_parquet_base64": base64.b64encode(research_path.read_bytes()).decode("ascii")
        if research_path.exists()
        else None,
        "source_status": source_status,
        "settings": settings,
        "indicators": indicators,
        "input_scope": "Exacte verwerkte historische invoer, scores en bronstatus van deze run.",
        "implementation": {
            str(path.relative_to(root)): path.read_text(encoding="utf-8")
            for path in sorted((root / "src/sol_reality_check").glob("*.py"))
        },
    }
    content = canonical_json(snapshot).encode()
    digest = sha256(content)
    path = root / f"data/research/inputs/{digest}.json.gz"
    atomic_create(path, gzip.compress(content, mtime=0))
    append_immutable(
        root / "data/research/runs.jsonl",
        {
            "run_at_utc": dashboard["generated_at_utc"],
            "data_cutoff_utc": dashboard["data_cutoff_utc"],
            "method_version": dashboard["method_version"],
            "input_sha256": digest,
            "file": str(path.relative_to(root)),
        },
        ["run_at_utc"],
    )


def verify_run_archives(root: Path) -> None:
    from sol_reality_check.ledger import read_jsonl
    from sol_reality_check.utils import payload_hash

    for row in read_jsonl(root / "data/research/runs.jsonl"):
        if row.get("payload_sha256") != payload_hash(row):
            raise ValueError("Run archive ledger hash mismatch")
        content = gzip.decompress((root / row["file"]).read_bytes())
        if sha256(content) != row["input_sha256"]:
            raise ValueError(f"Run input hash mismatch: {row['run_at_utc']}")


def verify_collected_history(root: Path) -> None:
    """Compare original ledger bytes and every original Parquet cell with the baseline."""
    directories = [root / "data/research/baseline"] + sorted(
        (root / "data/research/source_snapshots").glob("*/")
    )
    for directory in directories:
        _verify_history_snapshot(root, directory)
    parallel_snapshot = root / "data/research/parallel_snapshot"
    if parallel_snapshot.exists():
        _verify_history_snapshot(root, parallel_snapshot, check_ledger_prefix=False)


def _verify_history_snapshot(
    root: Path, directory: Path, check_ledger_prefix: bool = True
) -> None:
    verify_baseline(root, directory=directory)
    with tarfile.open(directory / "collected-data.tar.gz", mode="r:gz") as tar:
        for member in tar.getmembers():
            if not check_ledger_prefix or not member.name.startswith("data/ledger/"):
                continue
            handle = tar.extractfile(member)
            path = root / member.name
            if (
                handle is None
                or not path.exists()
                or not path.read_bytes().startswith(handle.read())
            ):
                raise ValueError(f"Collected ledger history changed: {member.name}")
        name = "data/curated/signaalonderzoek.parquet"
        if name not in tar.getnames():
            return
        handle = tar.extractfile(name)
        if handle is None:
            raise ValueError("Baseline Parquet missing")
        original = pd.read_parquet(io.BytesIO(handle.read())).set_index("run_at_utc")
        current = pd.read_parquet(root / name).set_index("run_at_utc")
        if current.index.has_duplicates or not original.index.isin(current.index).all():
            raise ValueError("Collected research runs were removed or duplicated")
        pd.testing.assert_frame_equal(
            original.sort_index(),
            current.loc[original.index, original.columns].sort_index(),
            check_dtype=False,
            check_exact=True,
        )
