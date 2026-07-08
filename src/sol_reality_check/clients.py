from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

LOGGER = logging.getLogger(__name__)
MAX_DAILY_PRICE_CHANGE = 0.40
MAX_TRUSTED_DAILY_PRICE_CHANGE = 0.75
CCXT_TIMEFRAME = "1d"
CCXT_LIMIT = 1000


class ApiError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, timeout: int = 20, retries: int = 3) -> None:
        self.timeout = timeout
        self.retries = retries

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self._request_json("get", url, **kwargs)

    def post_json(self, url: str, **kwargs: Any) -> Any:
        return self._request_json("post", url, **kwargs)

    def _request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                request = requests.post if method == "post" else requests.get
                response = request(url, timeout=self.timeout, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504}:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # pragma: no cover - exact request errors vary
                last = exc
                time.sleep(0.5 * (attempt + 1))
        raise ApiError(str(last))


def _coingecko_headers() -> dict[str, str]:
    api_key = os.getenv("COINGECKO_API_KEY")
    return {"x-cg-demo-api-key": api_key} if api_key else {}


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
    frame = repair_daily_price_outliers(
        frame,
        price_columns=["open", "high", "low", "close"],
        label=product_id,
    )
    return frame[["date", "asset", "open", "high", "low", "close", "volume"]]


def fetch_ccxt_consensus_daily(
    asset: str,
    exchange_configs: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    min_sources: int = 2,
    max_deviation_pct: float = 5.0,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    statuses: list[dict[str, Any]] = []
    symbol_key = f"{asset.lower()}_symbol"
    for config in exchange_configs:
        exchange_id = str(config["id"])
        symbol = str(config.get(symbol_key) or "")
        if not symbol:
            statuses.append(ccxt_status(exchange_id, symbol, False, "Symbol ontbreekt.", 0))
            continue
        try:
            frame = fetch_ccxt_exchange_daily(exchange_id, symbol, start, end)
            frames.append(frame)
            statuses.append(ccxt_status(exchange_id, symbol, True, "", len(frame)))
        except Exception as exc:  # pragma: no cover - exchange/network dependent
            statuses.append(ccxt_status(exchange_id, symbol, False, str(exc), 0))
    available = [status for status in statuses if status["available"]]
    if len(available) < min_sources:
        raise ApiError(f"CCXT consensus for {asset} has only {len(available)} sources")
    raw = pd.concat(frames, ignore_index=True)
    consensus = build_price_consensus(
        frames,
        asset=asset,
        min_sources=min_sources,
        max_deviation_pct=max_deviation_pct,
    )
    if consensus.empty:
        raise ApiError(f"CCXT consensus for {asset} returned no usable rows")
    price_breakdown = latest_price_breakdown(raw, consensus, asset, statuses)
    consensus.attrs["price_breakdown"] = price_breakdown
    consensus.attrs["ccxt_status"] = {
        "asset": asset.upper(),
        "available": True,
        "min_sources": min_sources,
        "max_deviation_pct": max_deviation_pct,
        "sources": statuses,
        "rows": len(consensus),
        "outlier_count": int(consensus["outlier_count"].sum()),
        "min_source_count": int(consensus["source_count"].min()),
        "max_source_count": int(consensus["source_count"].max()),
        "price_breakdown": price_breakdown,
    }
    return consensus


def latest_price_breakdown(
    raw: pd.DataFrame,
    consensus: pd.DataFrame,
    asset: str,
    statuses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    latest = consensus.sort_values("date").iloc[-1]
    latest_date = str(latest["date"])
    raw_day = raw[raw["date"] == latest_date].copy()
    median = float(latest["close"])
    max_deviation = float("nan")
    rows: list[dict[str, Any]] = []
    raw_by_exchange: dict[str, dict[str, Any]] = {}
    if not raw_day.empty:
        raw_day["deviation"] = (pd.to_numeric(raw_day["close"]) / median - 1).abs()
        max_deviation = float(raw_day["deviation"].max())
        raw_by_exchange = {str(row["exchange"]): dict(row) for _, row in raw_day.iterrows()}
    used_sources = set(str(latest["sources"]).split(","))
    status_by_exchange = {
        str(row.get("exchange")): row
        for row in (statuses or [])
        if isinstance(row, dict) and row.get("exchange")
    }
    exchange_names = sorted(set(raw_by_exchange) | set(status_by_exchange))
    for exchange in exchange_names:
        status = status_by_exchange.get(exchange, {})
        raw_row = raw_by_exchange.get(exchange)
        if raw_row is None:
            warning = str(status.get("warning") or "geen prijs op consensusdag")
            rows.append(
                {
                    "exchange": exchange,
                    "symbol": str(status.get("symbol") or ""),
                    "close": None,
                    "used": False,
                    "status": f"niet beschikbaar: {warning}",
                    "deviation_pct": None,
                }
            )
            continue
        rows.append(
            {
                "exchange": exchange,
                "symbol": str(raw_row["symbol"]),
                "close": round(float(raw_row["close"]), 8),
                "used": exchange in used_sources,
                "status": (
                    "succesvol gebruikt"
                    if exchange in used_sources
                    else "succesvol geladen; genegeerd"
                ),
                "deviation_pct": round(float(raw_row["deviation"]) * 100, 3),
            }
        )
    return {
        "asset": asset.upper(),
        "date": latest_date,
        "method": "Multi-exchange mediaan",
        "used_close": round(median, 8),
        "source_count": int(latest["source_count"]),
        "outlier_count": int(latest["outlier_count"]),
        "max_deviation_pct": None if pd.isna(max_deviation) else round(max_deviation * 100, 3),
        "exchange_prices": rows,
    }


def fetch_ccxt_exchange_daily(
    exchange_id: str,
    symbol: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    try:
        import ccxt
    except ImportError as exc:  # pragma: no cover - depends on installed env
        raise ApiError("ccxt is not installed") from exc
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})
    if not getattr(exchange, "has", {}).get("fetchOHLCV"):
        raise ApiError(f"{exchange_id} does not support fetchOHLCV")
    rows: list[list[float]] = []
    cursor = int(start.astimezone(UTC).timestamp() * 1000)
    end_ms = int(end.astimezone(UTC).timestamp() * 1000)
    while cursor < end_ms:
        payload = exchange.fetch_ohlcv(symbol, CCXT_TIMEFRAME, since=cursor, limit=CCXT_LIMIT)
        if not payload:
            break
        rows.extend(payload)
        last_ts = int(payload[-1][0])
        next_cursor = last_ts + 86_400_000
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(payload) < CCXT_LIMIT:
            break
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    if frame.empty:
        raise ApiError(f"No CCXT data for {exchange_id} {symbol}")
    frame["date"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True).dt.date.astype(str)
    start_date = pd.Timestamp(start).date().isoformat()
    end_date = pd.Timestamp(end).date().isoformat()
    frame = frame[(frame["date"] >= start_date) & (frame["date"] < end_date)]
    frame = frame.drop_duplicates("date", keep="last").sort_values("date")
    frame["exchange"] = exchange_id
    frame["symbol"] = symbol
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    frame = frame.dropna(subset=["close"])
    if frame.empty:
        raise ApiError(f"No usable CCXT close data for {exchange_id} {symbol}")
    return frame[["date", "exchange", "symbol", "close", "volume"]]


def build_price_consensus(
    frames: list[pd.DataFrame],
    asset: str,
    min_sources: int,
    max_deviation_pct: float,
) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True)
    rows: list[dict[str, Any]] = []
    max_deviation = max_deviation_pct / 100
    for date, group in raw.groupby("date"):
        closes = pd.to_numeric(group["close"], errors="coerce").dropna()
        if len(closes) < min_sources:
            continue
        median = float(closes.median())
        if median <= 0:
            continue
        group = group.assign(deviation=(pd.to_numeric(group["close"]) / median - 1).abs())
        usable = group[group["deviation"] <= max_deviation]
        if usable["exchange"].nunique() < min_sources:
            continue
        close = float(pd.to_numeric(usable["close"], errors="coerce").median())
        volume = pd.to_numeric(usable["volume"], errors="coerce").sum(min_count=1)
        rows.append(
            {
                "date": str(date),
                "asset": asset.upper(),
                "close": close,
                "volume": round(float(volume), 8) if not pd.isna(volume) else None,
                "source_count": int(usable["exchange"].nunique()),
                "outlier_count": int(len(group) - len(usable)),
                "sources": ",".join(sorted(usable["exchange"].unique())),
            }
        )
    if not rows:
        return pd.DataFrame()
    consensus = pd.DataFrame(rows).sort_values("date")
    consensus.attrs["price_breakdown"] = latest_price_breakdown(raw, consensus, asset)
    return consensus


def ccxt_status(
    exchange_id: str,
    symbol: str,
    available: bool,
    warning: str,
    rows: int,
) -> dict[str, Any]:
    return {
        "exchange": exchange_id,
        "symbol": symbol,
        "available": available,
        "warning": warning,
        "rows": rows,
    }


def repair_daily_price_outliers(
    frame: pd.DataFrame,
    price_columns: list[str],
    label: str,
    threshold: float = MAX_DAILY_PRICE_CHANGE,
    trusted_threshold: float = MAX_TRUSTED_DAILY_PRICE_CHANGE,
    trusted_dates: set[str] | None = None,
) -> pd.DataFrame:
    """Replace implausible daily close jumps with the previous valid price."""
    if frame.empty or "date" not in frame or "close" not in frame:
        return frame
    repaired = frame.sort_values("date").reset_index(drop=True).copy()
    repairs: list[dict[str, Any]] = []
    close_values = pd.to_numeric(repaired["close"], errors="coerce")
    previous_valid: float | None = None
    for idx, close in close_values.items():
        date = str(repaired.at[idx, "date"])
        if pd.isna(close) or float(close) <= 0:
            if previous_valid is not None:
                repairs.append(
                    price_repair_record(
                        repaired,
                        idx,
                        label,
                        close,
                        previous_valid,
                        "missing_or_non_positive",
                    )
                )
                set_price_columns(repaired, idx, price_columns, previous_valid)
            continue
        current = float(close)
        if previous_valid is not None:
            change = current / previous_valid - 1
            if trusted_dates and date in trusted_dates and abs(change) <= trusted_threshold:
                previous_valid = current
                continue
            if abs(change) > threshold:
                repairs.append(
                    price_repair_record(
                        repaired,
                        idx,
                        label,
                        current,
                        previous_valid,
                        f"daily_change_{change:.2%}",
                    )
                )
                set_price_columns(repaired, idx, price_columns, previous_valid)
                continue
        previous_valid = current
    if repairs:
        repaired.attrs["price_repairs"] = repairs
        LOGGER.warning(
            "Repaired %s suspicious daily price outlier(s) for %s", len(repairs), label
        )
    return repaired


def set_price_columns(
    frame: pd.DataFrame,
    idx: int,
    price_columns: list[str],
    value: float,
) -> None:
    for column in price_columns:
        if column in frame:
            frame.at[idx, column] = value


def price_repair_record(
    frame: pd.DataFrame,
    idx: int,
    label: str,
    original: Any,
    replacement: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "date": str(frame.at[idx, "date"]),
        "asset": label,
        "original_close": None if pd.isna(original) else round(float(original), 8),
        "replacement_close": round(float(replacement), 8),
        "reason": reason,
    }


def fetch_coingecko_current() -> dict[str, Any]:
    client = HttpClient()
    payload = client.get_json(
        "https://api.coingecko.com/api/v3/simple/price",
        headers=_coingecko_headers(),
        params={
            "ids": "solana,bitcoin",
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        },
    )
    if not isinstance(payload, dict) or "solana" not in payload or "bitcoin" not in payload:
        raise ApiError("Unexpected CoinGecko price response")
    return payload


def fetch_coingecko_breadth(cache_dir: Path, limit: int = 25) -> dict[str, Any]:
    category_id = resolve_solana_category(cache_dir)
    client = HttpClient()
    payload = client.get_json(
        "https://api.coingecko.com/api/v3/coins/markets",
        headers=_coingecko_headers(),
        params={
            "vs_currency": "usd",
            "category": category_id,
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h,7d",
        },
    )
    if not isinstance(payload, list):
        raise ApiError("Unexpected CoinGecko markets response")
    rows = [_normalise_market_row(row) for row in payload if isinstance(row, dict)]
    usable = [row for row in rows if _is_usable_ecosystem_token(row)]
    selected = usable[:limit]
    if not selected:
        raise ApiError("No usable CoinGecko Solana ecosystem tokens")
    positive_24h = sum((row.get("price_change_percentage_24h") or 0) > 0 for row in selected)
    positive_7d = sum((row.get("price_change_percentage_7d") or 0) > 0 for row in selected)
    returns_7d = [
        float(row["price_change_percentage_7d"]) / 100
        for row in selected
        if row.get("price_change_percentage_7d") is not None
    ]
    market_caps = [float(row["market_cap"]) for row in selected if row.get("market_cap")]
    total_cap = sum(market_caps)
    top3_cap = sum(market_caps[:3])
    spread_7d = (
        float(pd.Series(returns_7d).quantile(0.75) - pd.Series(returns_7d).quantile(0.25))
        if len(returns_7d) >= 4
        else None
    )
    breadth_notice = (
        "Experimentele indicator — nog onvoldoende historische waarnemingen voor een "
        "betrouwbare backtest."
    )
    return {
        "category_id": category_id,
        "token_count": len(selected),
        "positive_24h_share": round(positive_24h / len(selected), 4),
        "positive_7d_share": round(positive_7d / len(selected), 4),
        "median_return_7d": round(float(pd.Series(returns_7d).median()), 4)
        if returns_7d
        else None,
        "return_7d_spread": round(spread_7d, 4) if spread_7d is not None else None,
        "top3_market_cap_share": round(top3_cap / total_cap, 4) if total_cap else None,
        "historically_validated": False,
        "notice": breadth_notice,
        "tokens": selected,
    }


def resolve_solana_category(cache_dir: Path) -> str:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "coingecko_solana_category.txt"
    if cache_path.exists():
        cached = cache_path.read_text(encoding="utf-8").strip()
        if cached:
            return cached
    client = HttpClient()
    payload = client.get_json(
        "https://api.coingecko.com/api/v3/coins/categories/list",
        headers=_coingecko_headers(),
    )
    if not isinstance(payload, list):
        raise ApiError("Unexpected CoinGecko category response")
    matches = [
        row
        for row in payload
        if isinstance(row, dict)
        and "solana" in str(row.get("name", "")).lower()
        and "ecosystem" in str(row.get("name", "")).lower()
    ]
    if not matches:
        raise ApiError("CoinGecko Solana ecosystem category not found")
    category_id = str(matches[0]["category_id"])
    cache_path.write_text(category_id, encoding="utf-8")
    return category_id


def _normalise_market_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "symbol": str(row.get("symbol", "")).lower(),
        "name": row.get("name"),
        "current_price": row.get("current_price"),
        "market_cap": row.get("market_cap"),
        "total_volume": row.get("total_volume"),
        "price_change_percentage_24h": row.get("price_change_percentage_24h"),
        "price_change_percentage_7d": row.get("price_change_percentage_7d_in_currency"),
    }


def _is_usable_ecosystem_token(row: dict[str, Any]) -> bool:
    symbol = str(row.get("symbol", "")).lower()
    name = str(row.get("name", "")).lower()
    excluded_symbols = {"sol", "usdc", "usdt", "dai", "busd", "usd", "wbtc", "weth", "jitosol"}
    excluded_name_parts = ["wrapped", "stablecoin", "bridged", "wormhole"]
    if symbol in excluded_symbols or any(part in name for part in excluded_name_parts):
        return False
    market_cap = row.get("market_cap") or 0
    total_volume = row.get("total_volume") or 0
    return market_cap >= 1_000_000 and total_volume >= 25_000


def fetch_defillama_series() -> pd.DataFrame:
    client = HttpClient()
    frames = [
        _series_from_records(
            client.get_json("https://api.llama.fi/v2/historicalChainTvl/Solana"),
            "tvl",
            value_keys=("tvl", "totalLiquidityUSD", "totalTvl"),
        ),
        _series_from_records(
            client.get_json("https://stablecoins.llama.fi/stablecoincharts/Solana"),
            "stablecoins",
            value_keys=("totalCirculatingUSD", "totalCirculating", "circulating"),
        ),
        _series_from_records(
            client.get_json(
                "https://api.llama.fi/overview/dexs/Solana",
                params={"excludeTotalDataChart": "false", "excludeTotalDataChartBreakdown": "true"},
            ),
            "dex_volume",
            value_keys=("dailyVolume", "totalVolume", "volume"),
        ),
        _series_from_records(
            client.get_json(
                "https://api.llama.fi/overview/fees/Solana",
                params={"excludeTotalDataChart": "false", "excludeTotalDataChartBreakdown": "true"},
            ),
            "fees",
            value_keys=("dailyFees", "totalFees", "fees"),
        ),
    ]
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="date", how="outer")
    return merged.drop_duplicates("date").sort_values("date")


def _series_from_records(payload: Any, column: str, value_keys: tuple[str, ...]) -> pd.DataFrame:
    records = payload.get("totalDataChart", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ApiError(f"Unexpected DeFiLlama {column} response")
    rows: list[dict[str, Any]] = []
    for item in records:
        parsed = _parse_timeseries_item(item, value_keys)
        if parsed is not None:
            rows.append({"date": parsed[0], column: parsed[1]})
    if not rows:
        raise ApiError(f"Empty DeFiLlama {column} response")
    frame = pd.DataFrame(rows)
    frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=[column])
    return frame.drop_duplicates("date").sort_values("date")


def _parse_timeseries_item(item: Any, value_keys: tuple[str, ...]) -> tuple[str, float] | None:
    if isinstance(item, list | tuple) and len(item) >= 2:
        return _date_from_timestamp(item[0]), float(item[1])
    if not isinstance(item, dict):
        return None
    timestamp = item.get("date") or item.get("timestamp")
    if timestamp is None:
        return None
    value: Any = None
    for key in value_keys:
        if key in item:
            value = item[key]
            break
    if isinstance(value, dict):
        value = value.get("peggedUSD") or value.get("usd") or value.get("value")
    if value is None:
        return None
    return _date_from_timestamp(timestamp), float(value)


def _date_from_timestamp(value: Any) -> str:
    if isinstance(value, str) and "-" in value:
        return pd.to_datetime(value, utc=True).date().isoformat()
    return pd.to_datetime(int(value), unit="s", utc=True).date().isoformat()


def fetch_rpc_context() -> dict[str, Any]:
    url = os.getenv("SOLANA_RPC_URL") or "https://api.mainnet-beta.solana.com"
    client = HttpClient(retries=2)
    tx_count = client.post_json(
        url, json={"jsonrpc": "2.0", "id": 1, "method": "getTransactionCount"}
    )
    samples = client.post_json(
        url,
        json={"jsonrpc": "2.0", "id": 1, "method": "getRecentPerformanceSamples", "params": [3]},
    )
    return {
        "transaction_count": tx_count.get("result"),
        "recent_performance_samples": samples.get("result", []),
        "historically_validated": False,
    }
