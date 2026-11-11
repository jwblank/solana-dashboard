import base64
import gzip
import hashlib
import io
import json

import pandas as pd
import pytest
import yaml

from sol_reality_check.blue_explainer import COMPONENTS, FEATURES, cap_ceiling, explain_blue


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path
    (root / "config").mkdir()
    (root / "data/curated").mkdir(parents=True)
    (root / "data/research/inputs").mkdir(parents=True)
    (root / "config/indicators.yml").write_text(
        yaml.safe_dump({"analog_features": {f[0]: 1 for f in FEATURES}})
    )
    published = "2026-11-10T12:00:00Z"
    point = dict(
        date="2026-11-09",
        published_at=published,
        published_time=1,
        source_sha256="original",
        prediction_id="original",
        quality_score=55,
        sol_close=100,
    )
    prediction = dict(
        method_version="1.0.0",
        quality_caps=["Voorspelkwaliteit ≤ 0"],
        horizons={"7d": {"count": 32, "median_similarity": 80}},
    )
    pd.DataFrame(
        [
            dict(data_cutoff_utc="2026-11-09T23:59:59Z", run_at_utc=published, sol_return_7d=0.08),
            dict(
                data_cutoff_utc="2026-11-09T23:59:59Z",
                run_at_utc="2026-11-10T13:00:00Z",
                sol_return_7d=0.99,
            ),
        ]
    ).to_parquet(root / "data/curated/signaalonderzoek.parquet")
    components = {c[0]: 80 for c in COMPONENTS}
    components["stability"] = 70
    archive = {
        "dashboard": {
            "data_cutoff_utc": "2026-11-09T23:59:59Z",
            "current": {"sol_price": 100},
            "scores": {"evidence_quality": 55, "evidence_components": components},
        }
    }
    content = json.dumps(archive).encode()
    filename = "data/research/inputs/original.json.gz"
    (root / filename).write_bytes(gzip.compress(content))
    entry = dict(
        run_at_utc=published, file=filename, input_sha256=hashlib.sha256(content).hexdigest()
    )
    (root / "data/research/runs.jsonl").write_text(json.dumps(entry) + "\n")
    return root, point, prediction, entry


def test_original_cap_and_components_reconcile_without_source_writes(inputs):
    root, point, prediction, _ = inputs
    before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    rows, market, definitions = explain_blue(root, [point], {"original": prediction})
    row = rows[0]
    assert row["complete"]
    assert row["raw_score"] == 78
    assert row["ceiling"] == row["score"] == 55
    assert sum(c["weight"] for c in definitions) == pytest.approx(1)
    assert next(r for r in market if r["feature"] == "sol_return_7d")["value"] == 0.08
    assert before == {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_later_archive_never_backfills_old_publication(inputs):
    root, point, prediction, entry = inputs
    entry["run_at_utc"] = "2026-11-10T13:00:00Z"
    (root / "data/research/runs.jsonl").write_text(json.dumps(entry) + "\n")
    row = explain_blue(root, [point], {"original": prediction})[0][0]
    assert not row["complete"]
    assert row["raw_score"] is None
    assert row["data_quality"] is None
    assert row["stability"] is None  # Never invent the old 70 input.
    assert row["sample_adequacy"] == 80
    assert row["sample_adequacy_provenance"].startswith("Gereconstrueerd")


def test_missing_market_values_remain_missing(inputs):
    root, point, prediction, _ = inputs
    point["published_at"] = "2026-11-10T11:00:00Z"
    rows, market, _ = explain_blue(root, [point], {"original": prediction})
    assert not rows[0]["complete"]
    assert all(r["value"] is None for r in market)
    assert all(r["source_run_at"] is None for r in market)


def test_corrupt_archive_stops_export(inputs):
    root, point, prediction, entry = inputs
    entry["input_sha256"] = "wrong"
    (root / "data/research/runs.jsonl").write_text(json.dumps(entry) + "\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        explain_blue(root, [point], {"original": prediction})


@pytest.mark.parametrize("storage", ["json", "parquet"])
def test_exact_archived_input_precedes_rounded_research_row(inputs, storage):
    root, point, prediction, entry = inputs
    archive = json.loads(gzip.decompress((root / entry["file"]).read_bytes()))
    buffer = io.BytesIO()
    pd.DataFrame([{"date": point["date"], "sol_return_7d": 0.083217}]).to_parquet(buffer)
    content = buffer.getvalue()
    archive["history"] = {
        "bytes_base64": base64.b64encode(content).decode(),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    if storage == "json":
        archive["history"] = [{"date": point["date"], "sol_return_7d": 0.083217}]
    encoded = json.dumps(archive).encode()
    (root / entry["file"]).write_bytes(gzip.compress(encoded))
    entry["input_sha256"] = hashlib.sha256(encoded).hexdigest()
    (root / "data/research/runs.jsonl").write_text(json.dumps(entry) + "\n")
    _, market, _ = explain_blue(root, [point], {"original": prediction})
    feature = next(r for r in market if r["feature"] == "sol_return_7d")
    assert feature["value"] == 0.083217
    assert feature["provenance"].startswith("Exacte modelinvoer")


def test_context_warnings_do_not_create_a_cap():
    assert cap_ceiling(["RPC-netwerkcontext telt alleen actueel mee, niet in de backtest."]) is None
    assert cap_ceiling(["Minder dan 20 effectieve analogieën", "Voorspelkwaliteit ≤ 0"]) == 45
