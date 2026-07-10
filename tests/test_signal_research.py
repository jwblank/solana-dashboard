import json

import pandas as pd
import pytest

from sol_reality_check import pipeline
from sol_reality_check.validation import validate_signal_research


def dashboard(mode: str, generated: str, sol: float, btc: float) -> dict:
    return {
        "generated_at_utc": generated,
        "data_cutoff_utc": "2026-07-07T23:59:59Z",
        "method_version": "1.0.0",
        "mode": mode,
        "summary": {"regime": "mixed", "regime_title": "Gemengd marktbeeld"},
        "scores": {
            "market_signal": 58.0,
            "evidence_quality": 77.0,
            "blocks": {
                "price_strength": 62.0,
                "network_usage": 57.0,
                "capital": 51.0,
                "ecosystem_breadth": 58.0,
            },
        },
        "current": {"sol_price": sol, "btc_price": btc},
    }


def latest() -> pd.Series:
    return pd.Series(
        {
            "sol_return_1d": 0.01,
            "sol_return_7d": 0.02,
            "sol_return_30d": 0.03,
            "btc_return_7d": 0.01,
            "btc_return_30d": 0.02,
        }
    )


def isolate_signal_research_paths(monkeypatch, tmp_path):
    curated = tmp_path / "curated"
    site = tmp_path / "site"
    monkeypatch.setattr(pipeline, "CURATED", curated)
    monkeypatch.setattr(pipeline, "SITE_DATA", site)
    monkeypatch.setattr(pipeline, "SIGNAL_RESEARCH_PATH", curated / "signaalonderzoek.parquet")
    monkeypatch.setattr(pipeline, "SIGNAL_RESEARCH_LATEST_PATH", site / "signaalonderzoek.json")
    return curated, site


def test_demo_runs_do_not_pollute_production_signal_research(monkeypatch, tmp_path):
    curated, site = isolate_signal_research_paths(monkeypatch, tmp_path)

    pipeline.write_signal_research(
        dashboard("demo", "2026-07-08T18:55:03Z", 137.07, 46_570.57),
        latest(),
        "2026-07-08T18:55:03Z",
        "2026-07-07T23:59:59Z",
        "demo",
    )

    assert not (curated / "signaalonderzoek.parquet").exists()

    pipeline.write_signal_research(
        dashboard("production", "2026-07-08T18:55:19Z", 80.52, 63_323.27),
        latest(),
        "2026-07-08T18:55:19Z",
        "2026-07-07T23:59:59Z",
        "production",
    )

    research = json.loads((site / "signaalonderzoek.json").read_text(encoding="utf-8"))
    assert research["row_count_total"] == 1
    assert research["rows"][0]["mode"] == "production"
    assert research["rows"][0]["sol_price"] == 80.52
    parquet = pd.read_parquet(curated / "signaalonderzoek.parquet")
    assert parquet["mode"].tolist() == ["production"]
    assert "price_strength_weight" in parquet.columns


def test_signal_research_append_preserves_existing_rows_and_legacy_columns(monkeypatch, tmp_path):
    curated, _ = isolate_signal_research_paths(monkeypatch, tmp_path)
    path = curated / "signaalonderzoek.parquet"
    curated.mkdir(parents=True)
    old = pd.DataFrame(
        [
            {
                "run_at_utc": "2026-07-07T10:00:00Z",
                "data_cutoff_utc": "2026-07-06T23:59:59Z",
                "mode": "production",
                "sol_price": 75.0,
                "legacy_note": "keep me",
            }
        ]
    )
    old.to_parquet(path, index=False)
    old_hash = pipeline.dataframe_content_hash(old)

    pipeline.write_signal_research(
        dashboard("production", "2026-07-08T18:55:19Z", 80.52, 63_323.27),
        latest(),
        "2026-07-08T18:55:19Z",
        "2026-07-07T23:59:59Z",
        "production",
    )

    written = pd.read_parquet(path)
    assert len(written) == 2
    assert "legacy_note" in written.columns
    old_after = written[written["run_at_utc"] == "2026-07-07T10:00:00Z"][old.columns]
    assert pipeline.dataframe_content_hash(old_after) == old_hash
    weight_series = written.loc[
        written["run_at_utc"] == "2026-07-07T10:00:00Z",
        "price_strength_weight",
    ]
    assert weight_series.isna().all()


def test_signal_research_idempotent_same_row(monkeypatch, tmp_path):
    curated, _ = isolate_signal_research_paths(monkeypatch, tmp_path)
    args = (
        dashboard("production", "2026-07-08T18:55:19Z", 80.52, 63_323.27),
        latest(),
        "2026-07-08T18:55:19Z",
        "2026-07-07T23:59:59Z",
        "production",
    )
    pipeline.write_signal_research(*args)
    pipeline.write_signal_research(*args)
    written = pd.read_parquet(curated / "signaalonderzoek.parquet")
    assert len(written) == 1


def test_signal_research_conflicting_same_key_fails_without_change(monkeypatch, tmp_path):
    curated, _ = isolate_signal_research_paths(monkeypatch, tmp_path)
    path = curated / "signaalonderzoek.parquet"
    args = (
        dashboard("production", "2026-07-08T18:55:19Z", 80.52, 63_323.27),
        latest(),
        "2026-07-08T18:55:19Z",
        "2026-07-07T23:59:59Z",
        "production",
    )
    pipeline.write_signal_research(*args)
    before = path.read_bytes()

    with pytest.raises(pipeline.ApiError, match="key conflict"):
        pipeline.write_signal_research(
            dashboard("production", "2026-07-08T18:55:19Z", 81.00, 63_323.27),
            latest(),
            "2026-07-08T18:55:19Z",
            "2026-07-07T23:59:59Z",
            "production",
        )

    assert path.read_bytes() == before


def test_unreadable_existing_parquet_stops_without_replacement(monkeypatch, tmp_path):
    curated, _ = isolate_signal_research_paths(monkeypatch, tmp_path)
    path = curated / "signaalonderzoek.parquet"
    curated.mkdir(parents=True)
    path.write_bytes(b"not a parquet file")
    before = path.read_bytes()

    with pytest.raises(pipeline.ApiError, match="Cannot read existing"):
        pipeline.write_signal_research(
            dashboard("production", "2026-07-08T18:55:19Z", 80.52, 63_323.27),
            latest(),
            "2026-07-08T18:55:19Z",
            "2026-07-07T23:59:59Z",
            "production",
        )

    assert path.read_bytes() == before


def test_production_validation_rejects_demo_signal_research_row(tmp_path):
    data_dir = tmp_path / "site-data"
    data_dir.mkdir()
    (data_dir / "signaalonderzoek.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "mode": "demo",
                        "run_at_utc": "2026-07-08T18:55:03Z",
                        "sol_price": 137.07,
                        "btc_price": 46_570.57,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-production"):
        validate_signal_research(
            data_dir,
            dashboard("production", "2026-07-08T18:55:19Z", 80.52, 63_323.27),
        )
