from __future__ import annotations

import argparse
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from sol_reality_check.config import ROOT
from sol_reality_check.pipeline import (
    SIGNAL_RESEARCH_COLUMNS,
    SIGNAL_RESEARCH_PATH,
    dataframe_content_hash,
    parquet_snapshot,
    schema_union,
    validate_signal_research_write,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply an additive schema migration for signaalonderzoek.parquet."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply migration after making a backup.",
    )
    args = parser.parse_args()

    path = SIGNAL_RESEARCH_PATH
    if not path.exists():
        raise SystemExit(f"No source Parquet found at {path}")

    before = parquet_snapshot(path)
    frame = pd.read_parquet(path)
    target_columns = schema_union(frame.columns, SIGNAL_RESEARCH_COLUMNS)
    migrated = frame.reindex(columns=target_columns)
    old_hash = dataframe_content_hash(frame)
    migrated_old_hash = dataframe_content_hash(migrated.reindex(columns=frame.columns))
    added_columns = [column for column in target_columns if column not in frame.columns]

    print("Signal research migration")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"Path: {path}")
    print(f"Rows: {before['row_count']}")
    print(f"Columns before: {len(before['columns'])}")
    print(f"Columns after: {len(target_columns)}")
    print(f"Added columns: {', '.join(added_columns) if added_columns else 'none'}")
    print(f"run_at_utc min: {before['run_at_min']}")
    print(f"run_at_utc max: {before['run_at_max']}")
    print(f"Duplicate run_at_utc: {before['run_at_duplicates']}")
    print(f"File SHA-256 before: {before['file_sha256']}")
    print(f"Content hash before: {old_hash}")
    print(f"Content hash old cells after schema union: {migrated_old_hash}")
    print(f"Old rows unchanged: {old_hash == migrated_old_hash}")

    if old_hash != migrated_old_hash:
        raise SystemExit("Refusing migration: old cells would change")

    if not args.apply:
        print("Dry-run complete. Use --apply to write the additive schema migration.")
        return

    backup = backup_path(path)
    shutil.copy2(path, backup)
    print(f"Backup created: {backup}")
    tmp_path = path.with_name(f".{path.name}.migration.tmp")
    try:
        migrated.to_parquet(tmp_path, index=False)
        restored = pd.read_parquet(tmp_path)
        validate_signal_research_write(frame, migrated, restored, before)
        Path(ROOT / "site/data").mkdir(parents=True, exist_ok=True)
        restored.to_parquet(ROOT / "site/data/signaalonderzoek.parquet", index=False)
        tmp_path.replace(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    after = parquet_snapshot(path)
    print(f"File SHA-256 after: {after['file_sha256']}")
    print(f"Rows after: {after['row_count']}")
    print(f"Columns after: {len(after['columns'])}")
    print(f"Preserved historical rows: {before['row_count']} / {before['row_count']}")


def backup_path(path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.stem}.backup-{stamp}{path.suffix}")
    if backup.exists():
        raise SystemExit(f"Backup already exists: {backup}")
    return backup


if __name__ == "__main__":
    main()
