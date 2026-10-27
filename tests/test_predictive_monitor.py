from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from sol_reality_check.predictive_monitor import (
    SIGNAL_DEFINITION,
    append_immutable,
    generate_predictive_monitor,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def monitor_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "data" / "ledger").mkdir(parents=True)
    (root / "data" / "curated").mkdir(parents=True)
    (root / "site" / "data").mkdir(parents=True)
    shutil.copyfile(
        Path("data/ledger/predictions.jsonl"),
        root / "data" / "ledger" / "predictions.jsonl",
    )
    shutil.copyfile(
        Path("data/curated/signaalonderzoek.parquet"),
        root / "data" / "curated" / "signaalonderzoek.parquet",
    )
    return root


def test_monitor_preserves_sources_and_is_idempotent(tmp_path):
    root = monitor_root(tmp_path)
    predictions = root / "data" / "ledger" / "predictions.jsonl"
    research = root / "data" / "curated" / "signaalonderzoek.parquet"
    source_hashes = {path: sha256(path) for path in [predictions, research]}

    first = generate_predictive_monitor(root)
    ledger_paths = sorted((root / "data" / "ledger").glob("signal_*.jsonl"))
    ledger_bytes = {path.name: path.read_bytes() for path in ledger_paths}
    second = generate_predictive_monitor(root)

    assert first == second
    assert source_hashes == {path: sha256(path) for path in [predictions, research]}
    assert ledger_bytes == {path.name: path.read_bytes() for path in ledger_paths}
    for source in ledger_paths:
        assert source.read_bytes() == (root / "site" / "data" / source.name).read_bytes()


def test_monitor_backfills_known_events_without_claiming_confirmation(tmp_path):
    payload = generate_predictive_monitor(monitor_root(tmp_path))

    known_event_dates = {
        "2026-07-21",
        "2026-08-14",
        "2026-09-12",
        "2026-09-23",
        "2026-10-19",
    }
    events_by_date = {row["event_date"]: row for row in payload["events"]}

    assert known_event_dates <= events_by_date.keys()
    assert all(
        events_by_date[event_date]["evaluation_phase"] == "retrospective"
        for event_date in known_event_dates
    )
    assert payload["status"]["retrospective_mature_event_n"] == sum(
        row["status"] == "matured"
        and row["evaluation_phase"] == "retrospective"
        for row in payload["events"]
    )
    assert payload["status"]["prospective_mature_event_n"] == sum(
        row["status"] == "matured" and row["evaluation_phase"] == "prospective"
        for row in payload["events"]
    )
    if (
        payload["status"]["prospective_mature_event_n"]
        < payload["status"]["minimum_for_first_confirmation"]
    ):
        assert payload["status"]["code"] == "prospective_in_progress"
        assert payload["status"]["statistical_confirmation"] is False


def test_primary_metric_uses_independent_events_and_ready_controls(tmp_path):
    payload = generate_predictive_monitor(monitor_root(tmp_path))
    metric = next(
        row for row in payload["primary_metrics"] if row["metric_id"] == "sol_uplift_7d"
    )

    assert metric["independent_event_n"] == (
        metric["retrospective_event_n"] + metric["prospective_event_n"]
    )
    assert metric["independent_event_n"] > 0
    assert metric["control_window_n"] > 0
    assert metric["estimate"] == pytest.approx(
        metric["event_mean"] - metric["control_mean"]
    )
    assert metric["ci95"][0] <= metric["estimate"] <= metric["ci95"][1]


def test_immutable_ledger_rejects_changed_payload(tmp_path):
    path = tmp_path / "definitions.jsonl"
    append_immutable(path, SIGNAL_DEFINITION, ["definition_id"])
    changed = dict(SIGNAL_DEFINITION)
    changed["cooldown_days"] = 9

    with pytest.raises(ValueError, match="Immutable ledger conflict"):
        append_immutable(path, changed, ["definition_id"])
