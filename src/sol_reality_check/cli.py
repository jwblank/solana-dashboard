from __future__ import annotations

import argparse
import os

from sol_reality_check.config import ROOT, indicators, settings
from sol_reality_check.ledger import check_ledger
from sol_reality_check.pipeline import build_outputs, prepare_dataset
from sol_reality_check.validation import validate_outputs


def main() -> int:
    parser = argparse.ArgumentParser(prog="sol-reality-check")
    parser.add_argument(
        "command",
        choices=["bootstrap", "update", "backtest", "publish", "validate", "ledger-check"],
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
    return 1
