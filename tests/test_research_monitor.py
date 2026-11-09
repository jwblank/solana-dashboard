from __future__ import annotations

import base64
import copy
import gzip
import io
import json
import shutil
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sol_reality_check.ledger import read_jsonl, with_hash
from sol_reality_check.research_archive import (
    archive_run,
    ensure_baseline,
    verify_baseline,
    verify_collected_history,
    verify_run_archives,
)
from sol_reality_check.research_monitor import (
    build_inputs,
    generate_research_monitor,
    load_protocol,
    observed_return,
    summarize,
    validate_research_ledgers,
)
from sol_reality_check.shadow_quality import balanced_backtest


def make_root(tmp_path: Path, days: int = 120) -> Path:
    root = tmp_path / "project"
    for folder in ["config", "data/ledger", "data/curated", "site/data"]:
        (root / folder).mkdir(parents=True)
    shutil.copyfile("config/research_protocol.json", root / "config/research_protocol.json")
    rng = np.random.default_rng(4)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.025, days)))
    dates = pd.date_range("2026-07-04", periods=days)
    research, predictions = [], []
    for i, day in enumerate(dates):
        published = (day + pd.Timedelta(days=1, hours=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cutoff = day.strftime("%Y-%m-%dT23:59:59Z")
        prediction = {
            "prediction_id": str(day.date()),
            "created_at_utc": published,
            "data_cutoff_utc": cutoff,
            "method_version": "1.0.0",
            "feature_snapshot": {"sol_close": float(prices[i])},
            "market_signal": 50 + np.sin(i) * 10,
            "evidence_quality": 55 if day.dayofweek in [1, 4] else 80,
        }
        predictions.append(with_hash(prediction))
        research.append(
            {
                "run_at_utc": published,
                "data_cutoff_utc": cutoff,
                "mode": "production",
                "method_version": "1.0.0",
                "btc_price": float(50000 + i * 25),
                "network_usage_score": 50 + np.cos(i / 11) * 15,
            }
        )
    (root / "data/ledger/predictions.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in predictions)
    )
    pd.DataFrame(research).to_parquet(root / "data/curated/signaalonderzoek.parquet")
    return root


def test_baseline_and_forecasts_are_lossless_and_idempotent(tmp_path):
    root = make_root(tmp_path)
    sources = [
        root / "data/ledger/predictions.jsonl",
        root / "data/curated/signaalonderzoek.parquet",
    ]
    before = {p: p.read_bytes() for p in sources}
    now = pd.Timestamp("2026-11-09T16:00:00Z").to_pydatetime()
    first = generate_research_monitor(root, now)
    ledgers = list((root / "data/research").glob("*.jsonl"))
    registered = {p: p.read_bytes() for p in ledgers}
    second = generate_research_monitor(root, now + timedelta(hours=1))
    assert before == {p: p.read_bytes() for p in sources}
    assert registered == {p: p.read_bytes() for p in ledgers}
    assert first["candidates"] == second["candidates"]
    assert all(row["phase"] == "reconstructed" for row in first["records"])
    validate_research_ledgers(root)
    verify_collected_history(root)


def test_new_forecast_is_registered_before_entry_and_late_backfill_is_separate(tmp_path):
    root = make_root(tmp_path)
    latest = read_jsonl(root / "data/ledger/predictions.jsonl")[-1]
    published = pd.Timestamp(latest["created_at_utc"])
    protocol = load_protocol(root)
    protocol["locked_at_utc"] = (published - pd.Timedelta(minutes=1)).isoformat()
    (root / "config/research_protocol.json").write_text(json.dumps(protocol))
    payload = generate_research_monitor(root, (published + pd.Timedelta(minutes=1)).to_pydatetime())
    prospective = [r for r in payload["records"] if r["phase"] == "prospective"]
    assert len(prospective) == 12
    assert all(r["date"] == latest["data_cutoff_utc"][:10] for r in prospective)
    assert all(r["sol_return"] is None for r in prospective)
    assert all(r["probability_up"] is not None for r in prospective)
    late_root = make_root(tmp_path / "late")
    (late_root / "config/research_protocol.json").write_text(json.dumps(protocol))
    late = generate_research_monitor(late_root, (published + pd.Timedelta(days=1)).to_pydatetime())
    assert not any(r["phase"] == "prospective" for r in late["records"])


def test_future_sources_cannot_change_the_input_prefix(tmp_path):
    root = make_root(tmp_path)
    protocol = load_protocol(root)
    now = "2026-09-25T10:00:00Z"
    before, _ = build_inputs(root, protocol, now)
    path = root / "data/ledger/predictions.jsonl"
    rows = read_jsonl(path)
    for row in rows:
        if row["created_at_utc"] > now:
            row["evidence_quality"] = 0
            row["feature_snapshot"]["sol_close"] *= 10
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    after, _ = build_inputs(root, protocol, now)
    pd.testing.assert_frame_equal(before, after)


def test_components_published_later_are_not_available_for_earlier_prediction(tmp_path):
    root = make_root(tmp_path)
    path = root / "data/curated/signaalonderzoek.parquet"
    rows = pd.read_parquet(path)
    rows.loc[80, "run_at_utc"] = "2026-09-24T20:00:00Z"
    rows.to_parquet(path)
    frame, _ = build_inputs(root, load_protocol(root), "2026-11-09T16:00:00Z")
    assert pd.isna(frame.iloc[80].network)
    assert pd.isna(frame.iloc[80].btc)


def test_outcome_waits_until_endpoint_price_is_published():
    prices = {
        "2026-11-01": {"sol": 100, "sol_available_at": "2026-11-02T09:00:00Z"},
        "2026-11-08": {"sol": 110, "sol_available_at": "2026-11-09T11:00:00Z"},
    }
    assert (
        observed_return(prices, "2026-11-01", "2026-11-08", "sol", "2026-11-09T10:00:00Z") is None
    )
    assert observed_return(
        prices, "2026-11-01", "2026-11-08", "sol", "2026-11-09T12:00:00Z"
    ) == pytest.approx(0.1)
    assert (
        observed_return(prices, "2026-11-02", "2026-11-08", "sol", "2026-11-09T12:00:00Z") is None
    )


def test_baseline_tampering_and_removed_history_are_detected(tmp_path):
    root = make_root(tmp_path)
    ensure_baseline(root)
    path = root / "data/ledger/predictions.jsonl"
    path.write_text("\n".join(path.read_text().splitlines()[1:]) + "\n")
    with pytest.raises(ValueError, match="history changed"):
        verify_collected_history(root)
    archive = root / "data/research/baseline/collected-data.tar.gz"
    archive.write_bytes(archive.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_baseline(root)


def test_archive_run_keeps_exact_inputs_and_detects_corruption(tmp_path):
    root = make_root(tmp_path)
    dashboard = {
        "generated_at_utc": "2026-11-09T09:00:00Z",
        "data_cutoff_utc": "2026-11-08T23:59:59Z",
        "method_version": "1.0.0",
    }
    archive_run(root, dashboard, pd.DataFrame({"value": [1, np.nan]}), {}, {}, {})
    archive_run(root, dashboard, pd.DataFrame({"value": [1, np.nan]}), {}, {}, {})
    assert len(read_jsonl(root / "data/research/runs.jsonl")) == 1
    verify_run_archives(root)
    stored = next((root / "data/research/inputs").glob("*.gz"))
    snapshot = json.loads(gzip.decompress(stored.read_bytes()))
    restored = pd.read_parquet(io.BytesIO(base64.b64decode(snapshot["history"]["bytes_base64"])))
    pd.testing.assert_frame_equal(restored, pd.DataFrame({"value": [1, np.nan]}), check_exact=True)
    assert (
        base64.b64decode(snapshot["research_parquet_base64"])
        == (root / "data/curated/signaalonderzoek.parquet").read_bytes()
    )
    stored.write_bytes(b"corrupt")
    with pytest.raises((ValueError, OSError)):
        verify_run_archives(root)


def test_direction_counts_and_comparison_are_paired():
    rows = []
    for i, (actual, prediction) in enumerate([(0.1, 0.7), (-0.1, 0.3), (-0.05, 0.8)]):
        rows.append(
            {
                "entry_date": f"2026-10-{i + 1:02d}",
                "exit_date": f"2026-10-{i + 8:02d}",
                "sol_return": actual,
                "relative_return": actual - 0.01,
                "probability_up": prediction,
                "predicted_direction": "up" if prediction >= 0.5 else "down",
                "active": True,
                "brier": (prediction - int(actual > 0)) ** 2,
                "baseline_brier": 0.25,
            }
        )
    result = summarize(rows, 7)
    assert result["up_correct_n"] == 1
    assert result["down_correct_n"] == 1
    assert result["actual_down_n"] == 2
    assert result["balanced_accuracy"] == 0.75
    assert result["brier_improvement"] == pytest.approx(0.25 - (0.09 + 0.09 + 0.64) / 3)
    assert result["nonoverlap_n"] == 1
    assert result["brier_improvement_ci95"] == [None, None]
    assert summarize([], 7)["brier"] is None


def test_calendar_balanced_shadow_uses_all_weekdays_equally(monkeypatch):
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=800).strftime("%Y-%m-%d"),
            "sol_close": 100 + np.sin(np.arange(800)),
        }
    )

    def analogs(_frame, idx, _weights, horizon):
        assert idx + horizon < len(frame)
        return pd.DataFrame({f"return_{horizon}d": [0.1, -0.1] * 10, "similarity": [50] * 20})

    monkeypatch.setattr("sol_reality_check.shadow_quality.find_analogs", analogs)
    result = balanced_backtest(frame, {})
    assert result["available"] is True
    assert result["weekdays_n"] == [26] * 7
    assert len(result["test_rows"]) == 182
    assert pd.Timestamp(result["from"]).dayofweek == 0
    assert pd.Timestamp(result["through"]).dayofweek == 6
    broken = frame.drop(index=700).reset_index(drop=True)
    assert balanced_backtest(broken, {})["available"] is False


def test_changed_protocol_cannot_overwrite_registered_definition(tmp_path):
    root = make_root(tmp_path, 20)
    now = pd.Timestamp("2026-11-09T16:00:00Z").to_pydatetime()
    generate_research_monitor(root, now)
    protocol = copy.deepcopy(load_protocol(root))
    protocol["network_threshold"] = 49
    (root / "config/research_protocol.json").write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="Immutable ledger conflict"):
        generate_research_monitor(root, now)
