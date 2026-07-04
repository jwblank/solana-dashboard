from sol_reality_check.ledger import append_unique, check_ledger, read_jsonl


def test_ledger_hash_and_duplicate_guard(tmp_path):
    pred = tmp_path / "predictions.jsonl"
    out = tmp_path / "outcomes.jsonl"
    payload = {
        "prediction_id": "2026-07-04__method-v1.0.0",
        "created_at_utc": "2026-07-04T00:00:00Z",
        "data_cutoff_utc": "2026-07-03T23:59:59Z",
        "method_version": "1.0.0",
        "regime": "mixed",
        "market_signal": 50,
        "evidence_quality": 55,
        "horizons": {},
        "source_status": {},
        "feature_snapshot": {},
        "quality_caps": [],
    }
    assert append_unique(pred, payload, ["prediction_id"])
    assert not append_unique(pred, payload, ["prediction_id"])
    assert len(read_jsonl(pred)) == 1
    assert check_ledger(pred, out) == []
