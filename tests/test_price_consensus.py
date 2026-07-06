import pandas as pd

from sol_reality_check.clients import build_price_consensus


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
