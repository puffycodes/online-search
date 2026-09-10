#!/usr/bin/env python3
"""
Shared helpers for pulling price history from Yahoo Finance's public chart
endpoint. No API key or authentication required.

Used by stock_close_history.py and stock_candlestick.py. Each of those scripts
keeps its own row shaping (rounding, date formatting, which rows to drop) and
its own output stage; everything up to and including the HTTP call and the
raw-payload navigation lives here.
"""

import datetime as dt

import requests

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# Yahoo rejects requests without a browser-like User-Agent.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
REQUEST_TIMEOUT = 15

VALID_RANGES = [
    "5d", "1mo", "3mo", "6mo", "ytd", "1y", "2y", "5y", "10y", "max",
]
SECONDS_PER_DAY = 86400


def parse_date(value):
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise ValueError(f"invalid date {value!r}, expected YYYY-MM-DD")


def build_params(interval="1d", range_=None, start=None, end=None, last=None):
    """Return the query params for the chart call.

    The window is chosen by, in priority order: an explicit start/end pair,
    then --last N, then a --range keyword. The --last look-back window is
    widened for coarser intervals so N whole bars are actually covered.
    """
    params = {"interval": interval, "includeAdjustedClose": "true"}

    if start or end:
        start_dt = parse_date(start) if start else None
        end_dt = parse_date(end) if end else dt.datetime.now(dt.timezone.utc)
        if start_dt is None:
            raise ValueError("--end requires --start")
        if end_dt <= start_dt:
            raise ValueError("--end must be after --start")
        params["period1"] = int(start_dt.timestamp())
        # pad the end by a day so the final session is inclusive
        params["period2"] = int(end_dt.timestamp()) + SECONDS_PER_DAY
    elif last:
        # Fetch a generous calendar window, then let the caller trim to the
        # last N rows. ~1.6 calendar days per trading day, plus slack for
        # holidays; more for weekly/monthly bars.
        lookback_days = last * 2 + 10
        if interval == "1wk":
            lookback_days = last * 9 + 14
        elif interval == "1mo":
            lookback_days = last * 32 + 31
        start_dt = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)
        params["period1"] = int(start_dt.timestamp())
        params["period2"] = int(dt.datetime.now(dt.timezone.utc).timestamp()) + SECONDS_PER_DAY
    else:
        params["range"] = range_

    return params


def fetch_history(symbol, params):
    response = requests.get(
        CHART_URL.format(symbol=symbol),
        params=params,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    # Yahoo returns a JSON error body with a 404/400 for bad symbols.
    try:
        payload = response.json()
    except ValueError:
        response.raise_for_status()
        raise
    error = payload.get("chart", {}).get("error")
    if error:
        raise requests.RequestException(
            error.get("description") or error.get("code") or str(error)
        )
    results = payload.get("chart", {}).get("result")
    if not results:
        raise requests.RequestException("no data returned for symbol")
    return results[0]


def meta_summary(meta, fallback_symbol=None):
    """Pull the display fields out of a chart result's ``meta`` block.

    Returns a ``(symbol, exchange, currency)`` tuple: ``symbol`` falls back
    to ``fallback_symbol`` then ``"?"``, ``exchange`` to ``"?"``, and
    ``currency`` to ``""`` when the payload does not carry them.
    """
    symbol = meta.get("symbol") or fallback_symbol or "?"
    exchange = meta.get("fullExchangeName") or meta.get("exchangeName") or "?"
    currency = meta.get("currency") or ""
    return symbol, exchange, currency


def extract_series(result):
    """Return (meta, series) from a Yahoo chart result.

    series is a dict of parallel lists straight off the payload - "timestamp",
    "open", "high", "low", "close", "volume" - plus "adjclose" (a list or
    None) and the resolved "gmtoffset". Callers turn these into rows.
    """
    meta = result.get("meta", {})
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    adj_block = result.get("indicators", {}).get("adjclose") or [{}]
    adj_closes = adj_block[0].get("adjclose") if adj_block else None
    return meta, {
        "gmtoffset": meta.get("gmtoffset", 0) or 0,
        "timestamp": result.get("timestamp") or [],
        "open": quote.get("open") or [],
        "high": quote.get("high") or [],
        "low": quote.get("low") or [],
        "close": quote.get("close") or [],
        "volume": quote.get("volume") or [],
        "adjclose": adj_closes,
    }
