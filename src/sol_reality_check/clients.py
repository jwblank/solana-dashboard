from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import requests


class ApiError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, timeout: int = 20, retries: int = 3) -> None:
        self.timeout = timeout
        self.retries = retries

    def get_json(self, url: str, **kwargs: Any) -> Any:
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = requests.get(url, timeout=self.timeout, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504}:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # pragma: no cover - exact request errors vary
                last = exc
                time.sleep(0.5 * (attempt + 1))
        raise ApiError(str(last))


def fetch_coinbase_daily(product_id: str, start: datetime, end: datetime) -> pd.DataFrame:
    client = HttpClient()
    rows: list[list[float]] = []
    cursor = start.astimezone(UTC)
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=300), end)
        payload = client.get_json(
            f"https://api.exchange.coinbase.com/products/{product_id}/candles",
            params={
                "granularity": 86400,
                "start": cursor.isoformat(),
                "end": chunk_end.isoformat(),
            },
        )
        if not isinstance(payload, list):
            raise ApiError(f"Unexpected Coinbase response for {product_id}")
        rows.extend(payload)
        cursor = chunk_end
    frame = pd.DataFrame(rows, columns=["timestamp", "low", "high", "open", "close", "volume"])
    if frame.empty:
        raise ApiError(f"No Coinbase data for {product_id}")
    frame["date"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True).dt.date.astype(str)
    frame = frame.drop_duplicates("date").sort_values("date")
    frame["asset"] = product_id.split("-")[0]
    return frame[["date", "asset", "open", "high", "low", "close", "volume"]]


def fetch_defillama_series() -> pd.DataFrame:
    client = HttpClient()
    tvl = client.get_json("https://api.llama.fi/v2/historicalChainTvl/Solana")
    if not isinstance(tvl, list):
        raise ApiError("Unexpected DeFiLlama TVL response")
    frame = pd.DataFrame(tvl)
    frame["date"] = pd.to_datetime(frame["date"], unit="s", utc=True).dt.date.astype(str)
    frame = frame.rename(columns={"tvl": "tvl"})
    return frame[["date", "tvl"]].drop_duplicates("date").sort_values("date")


def fetch_rpc_context() -> dict[str, Any]:
    url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    client = HttpClient(retries=2)
    tx_count = client.get_json(
        url, json={"jsonrpc": "2.0", "id": 1, "method": "getTransactionCount"}
    )
    samples = client.get_json(
        url,
        json={"jsonrpc": "2.0", "id": 1, "method": "getRecentPerformanceSamples", "params": [3]},
    )
    return {
        "transaction_count": tx_count.get("result"),
        "recent_performance_samples": samples.get("result", []),
        "historically_validated": False,
    }
