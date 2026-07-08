import pandas as pd

from sol_reality_check.clients import build_price_consensus, latest_price_breakdown
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


def test_latest_price_breakdown_lists_exchange_inputs():
    raw_frames = [
        exchange_frame("kraken", [100.0, 101.0]),
        exchange_frame("coinbase", [100.5, 29.5]),
        exchange_frame("okx", [99.5, 102.0]),
    ]
    consensus = build_price_consensus(
        raw_frames,
        asset="sol",
        min_sources=2,
        max_deviation_pct=5.0,
    )
    breakdown = latest_price_breakdown(pd.concat(raw_frames), consensus, "sol")

    assert breakdown["used_close"] == 101.5
    assert breakdown["source_count"] == 2
    assert [row["exchange"] for row in breakdown["exchange_prices"]] == [
        "coinbase",
        "kraken",
        "okx",
    ]
    assert [row["used"] for row in breakdown["exchange_prices"]] == [False, True, True]


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


def test_source_row_labels_gap_fill_as_partial_and_exposes_price_breakdown():
    row = source_row(
        "CCXT consensus",
        {
            "available": False,
            "context": {
                "sol": {
                    "fallback_used": True,
                    "provider": "CCXT consensus + Coinbase gap fill",
                    "price_breakdown": {
                        "date": "2026-07-06",
                        "method": "Coinbase gap fill",
                        "used_close": 81.89,
                        "source_count": 1,
                        "outlier_count": 0,
                        "gap_fill_start": "2023-07-03",
                        "ccxt_last_date": "2023-07-02",
                        "ccxt_last_close": 19.459,
                        "exchange_prices": [],
                    },
                }
            },
        },
        "Multi-exchange SOL/BTC dagprijs",
        "Historisch gevalideerd",
        "1400 consensusrijen",
    )

    assert row["status"] == "Coinbase herstelbron"
    assert row["last_success_at_utc"] == "Echte Coinbase-data gebruikt"
    assert row["price_breakdown"][0]["used_close"] == 81.89
    assert "Geen fake data" in row["warning"]


def test_latest_price_breakdown_lists_failed_exchange_status():
    raw_frames = [
        exchange_frame("kraken", [100.0, 101.0]),
        exchange_frame("kucoin", [100.5, 101.5]),
    ]
    consensus = build_price_consensus(
        raw_frames,
        asset="sol",
        min_sources=2,
        max_deviation_pct=5.0,
    )
    breakdown = latest_price_breakdown(
        pd.concat(raw_frames),
        consensus,
        "sol",
        [
            {
                "exchange": "kraken",
                "symbol": "SOL/USD",
                "available": True,
                "warning": "",
                "rows": 2,
            },
            {
                "exchange": "kucoin",
                "symbol": "SOL/USDT",
                "available": True,
                "warning": "",
                "rows": 2,
            },
            {
                "exchange": "okx",
                "symbol": "SOL/USDT",
                "available": False,
                "warning": "rate limit",
                "rows": 0,
            },
        ],
    )

    okx = [row for row in breakdown["exchange_prices"] if row["exchange"] == "okx"][0]
    assert okx["close"] is None
    assert okx["status"] == "niet beschikbaar: rate limit"
