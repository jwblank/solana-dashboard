import pandas as pd

from sol_reality_check.clients import build_price_consensus
from sol_reality_check.pipeline import source_row


def exchange_frame(exchange: str, closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-07-01", "2026-07-02"],
            "exchange": [exchange, exchange],
            "symbol": ["SOL/USD", "SOL/USD"],
            "close": closes,
            "volume": [1000.0, 1000.0],
        }
    )


def test_price_consensus_uses_median_and_ignores_exchange_outlier():
    consensus = build_price_consensus(
        [
            exchange_frame("kraken", [100.0, 101.0]),
            exchange_frame("coinbase", [100.5, 29.5]),
            exchange_frame("okx", [99.5, 102.0]),
        ],
        asset="sol",
        min_sources=2,
        max_deviation_pct=5.0,
    )

    latest = consensus.iloc[-1]

    assert latest["close"] == 101.5
    assert latest["source_count"] == 2
    assert latest["outlier_count"] == 1
    assert latest["sources"] == "kraken,okx"


def test_price_consensus_skips_day_when_too_few_sources_remain():
    consensus = build_price_consensus(
        [
            exchange_frame("kraken", [100.0, 101.0]),
            exchange_frame("coinbase", [100.5, 29.5]),
        ],
        asset="sol",
        min_sources=2,
        max_deviation_pct=5.0,
    )

    assert consensus["date"].tolist() == ["2026-07-01"]


def test_source_row_labels_price_fallback_clearly():
    row = source_row(
        "CCXT consensus",
        {
            "available": False,
            "context": {
                "sol": {"fallback_used": True, "provider": "Coinbase fallback"},
                "btc": {"fallback_used": False, "provider": "CCXT consensus"},
            },
        },
        "Multi-exchange SOL/BTC dagprijs",
        "Historisch gevalideerd",
        "1400 consensusrijen",
    )

    assert row["status"] == "Fallback gebruikt"
    assert row["last_success_at_utc"] == "Coinbase fallback actief"
    assert "fallback" in row["warning"]
