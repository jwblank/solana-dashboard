from __future__ import annotations

import argparse
import json
import os

from sol_reality_check.config import ROOT, indicators, settings
from sol_reality_check.ledger import check_ledger
from sol_reality_check.pipeline import (
    ApiError,
    build_outputs,
    expected_latest_history_date,
    prepare_dataset,
)
from sol_reality_check.validation import validate_outputs


def main() -> int:
    parser = argparse.ArgumentParser(prog="sol-reality-check")
    parser.add_argument(
        "command",
        choices=[
            "bootstrap",
            "update",
            "backtest",
            "publish",
            "validate",
            "ledger-check",
            "freshness-check",
        ],
    )
    args = parser.parse_args()
    mode = os.getenv("APP_MODE", "demo")
    settings()
    indicators()
    if args.command in {"bootstrap", "update", "publish"}:
        build_outputs(mode)
        return 0
    if args.command == "backtest":
        prepare_dataset(mode)
        build_outputs(mode)
        return 0
    if args.command == "validate":
        validate_outputs()
        return 0
    if args.command == "ledger-check":
        errors = check_ledger(
            ROOT / "data/ledger/predictions.jsonl", ROOT / "data/ledger/outcomes.jsonl"
        )
        if errors:
            for error in errors:
                print(error)
            return 1
        print("Ledger integrity OK")
        return 0
    if args.command == "freshness-check":
        dashboard_path = ROOT / "site/data/dashboard.json"
        dashboard = json.loads(dashboard_path.read_text())
        cutoff = str(dashboard.get("data_cutoff_utc", ""))[:10]
        expected = expected_latest_history_date()
        if cutoff < expected:
            raise ApiError(
                f"Dashboard data is stale: data_cutoff_utc={dashboard.get('data_cutoff_utc')}, "
                f"expected at least {expected}T23:59:59Z."
            )
        print(f"Dashboard freshness OK: {dashboard.get('data_cutoff_utc')}")
        return 0
    return 1
