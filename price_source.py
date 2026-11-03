#!/usr/bin/env python3
"""
Shared price-history source for stock_price_history.py, stock_candlestick_chart.py,
stock_rebased_chart.py and stock_risk.py, in place of Yahoo Finance's chart
endpoint (which fails the source audit, docs/source-audit.md).

daily_history(symbol, params) takes a ticker in Yahoo notation and the params
yahoo_finance.build_params() makes, routes the ticker to a keyed provider, and
returns the daily (or weekly / monthly) bars in stock_data.daily_history()'s
provider-neutral shape; the scripts reach it through stock_data.py. Routing,
as decided on 2026-10-21 (docs/things-to-explore.md):

- EODHD (EODHD_API_KEY) for US stocks (no suffix), the exchanges in
  EODHD_EXCHANGES (.L, .DE, .PA, .TO, .AX, .HK, ...), indices (^GSPC ->
  GSPC.INDX), currency pairs (EURUSD=X -> EURUSD.FOREX) and crypto
  (BTC-USD -> BTC-USD.CC).
- Alpha Vantage (ALPHAVANTAGE_API_KEY) for India: .NS and .BO -> .BSE.
- Singapore (.SI), Tokyo (.T) and futures (=F) are refused for now: no
  configured source covers them.

Weekly and monthly bars are built here from the daily ones. Notes about the
data (EODHD's free-plan warning, Alpha Vantage's 100-session limit) come back
in "notes"; "source" names the provider.

Not a CLI itself - this module is imported, not run.
"""

import datetime as dt
import os
import re
import time

import requests

import alphavantage_price_history as avph
import daily_prices
import eodhd_price_history as eodph
from cli_utils import load_dotenv

# Yahoo suffix -> (EODHD exchange code, exchange name, currency). Codes and
# names come from EODHD's exchanges-list; US, LSE, XETRA, PA, TO, AU and HK
# were tested on 2026-10-21. LSE and JSE quote in minor units, as on Yahoo.
EODHD_EXCHANGES = {
    "": ("US", "USA Stocks", "USD"),
    "L": ("LSE", "London Exchange", "GBp"),
    "DE": ("XETRA", "XETRA Stock Exchange", "EUR"),
    "F": ("F", "Frankfurt Exchange", "EUR"),
    "PA": ("PA", "Euronext Paris", "EUR"),
    "AS": ("AS", "Euronext Amsterdam", "EUR"),
    "BR": ("BR", "Euronext Brussels", "EUR"),
    "LS": ("LS", "Euronext Lisbon", "EUR"),
    "MC": ("MC", "Madrid Exchange", "EUR"),
    "SW": ("SW", "SIX Swiss Exchange", "CHF"),
    "VI": ("VI", "Vienna Exchange", "EUR"),
    "ST": ("ST", "Stockholm Exchange", "SEK"),
    "OL": ("OL", "Oslo Stock Exchange", "NOK"),
    "CO": ("CO", "Copenhagen Exchange", "DKK"),
    "HE": ("HE", "Helsinki Exchange", "EUR"),
    "IR": ("IR", "Irish Exchange", "EUR"),
    "TO": ("TO", "Toronto Exchange", "CAD"),
    "V": ("V", "TSX Venture Exchange", "CAD"),
    "AX": ("AU", "Australian Securities Exchange", "AUD"),
    "HK": ("HK", "Hong Kong Exchange", "HKD"),
    "KS": ("KO", "Korea Stock Exchange", "KRW"),
    "KQ": ("KQ", "KOSDAQ", "KRW"),
    "SS": ("SHG", "Shanghai Stock Exchange", "CNY"),
    "SZ": ("SHE", "Shenzhen Stock Exchange", "CNY"),
    "TW": ("TW", "Taiwan Stock Exchange", "TWD"),
    "TWO": ("TWO", "Taiwan OTC Exchange", "TWD"),
    "JK": ("JK", "Jakarta Exchange", "IDR"),
    "BK": ("BK", "Thailand Exchange", "THB"),
    "KL": ("KLSE", "Kuala Lumpur Exchange", "MYR"),
    "JO": ("JSE", "Johannesburg Exchange", "ZAc"),
    "SA": ("SA", "Sao Paulo Exchange", "BRL"),
    "MX": ("MX", "Mexican Exchange", "MXN"),
}
# Yahoo suffix -> (Alpha Vantage suffix, exchange name, currency). Alpha
# Vantage has India's BSE listings, not NSE ones, so .NS maps to .BSE too.
ALPHAVANTAGE_EXCHANGES = {
    "NS": ("BSE", "BSE", "INR"),
    "BO": ("BSE", "BSE", "INR"),
}
# Markets left out for now (2026-10-21); neither provider was found to cover them.
UNSUPPORTED_EXCHANGES = {"SI": "Singapore", "T": "Tokyo"}
# Quote currencies that mark a Yahoo crypto ticker (BTC-USD), as opposed to a
# share class such as BRK-B.
CRYPTO_QUOTES = {"USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "HKD", "SGD",
                 "KRW", "INR", "CNY", "BTC", "ETH", "USDT"}
CRYPTO_RE = re.compile(r"^([A-Z0-9]+)-([A-Z]+)$")

PROVIDERS = {"eodhd": "EODHD", "alphavantage": "Alpha Vantage"}
KEYS = {
    "eodhd": ("EODHD_API_KEY", "eodhd_price_history.py"),
    "alphavantage": ("ALPHAVANTAGE_API_KEY", "alphavantage_price_history.py"),
}

# Calendar days behind each yahoo_finance.VALID_RANGES keyword ("5d" is the
# last 5 sessions, "ytd" starts on 1 January, "max" asks for everything).
RANGE_DAYS = {"1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "2y": 731,
              "5y": 1827, "10y": 3653}
FIVE_DAY_LOOKBACK = 12
EARLIEST = dt.date(1900, 1, 1)
SECONDS_PER_DAY = 86400
# Free Alpha Vantage keys refuse a second request within a second ("1 request
# per second"), which a multi-symbol run of rebased chart or risk would hit.
ALPHAVANTAGE_MIN_GAP = 1.1
_last_alphavantage_call = 0.0


def route(symbol):
    """Return ``(provider, provider_symbol, exchange, currency)`` for a Yahoo ticker.

    Raises ``ValueError`` for futures, a market left out for now, or an
    exchange suffix no provider is set up for.
    """
    ticker = symbol.strip().upper()
    if ticker.endswith("=F"):
        raise ValueError("futures (=F) aren't supported yet: no configured price source covers them")
    if ticker.startswith("^"):
        return "eodhd", f"{ticker[1:]}.INDX", "Index", "points"
    if ticker.endswith("=X"):
        pair = ticker[:-2]
        if len(pair) == 3:
            # Yahoo's JPY=X is USD/JPY.
            pair = "USD" + pair
        return "eodhd", f"{pair}.FOREX", "Currency", pair[3:]
    match = CRYPTO_RE.match(ticker)
    if match and match.group(2) in CRYPTO_QUOTES:
        return "eodhd", f"{ticker}.CC", "Cryptocurrency", match.group(2)

    base, _, suffix = ticker.rpartition(".")
    if not base:
        base, suffix = ticker, ""
    if suffix in UNSUPPORTED_EXCHANGES:
        raise ValueError(
            f"{UNSUPPORTED_EXCHANGES[suffix]} listings (.{suffix}) aren't supported "
            f"for now: no configured price source covers them"
        )
    if suffix in ALPHAVANTAGE_EXCHANGES:
        code, name, currency = ALPHAVANTAGE_EXCHANGES[suffix]
        return "alphavantage", f"{base}.{code}", name, currency
    if suffix in EODHD_EXCHANGES:
        code, name, currency = EODHD_EXCHANGES[suffix]
        return "eodhd", f"{base}.{code}", name, currency
    raise ValueError(f"no price source is set up for the exchange suffix .{suffix}")


def window(params, today=None):
    """Return ``(first, final, keep)`` from yahoo_finance.build_params() output.

    ``first`` and ``final`` are inclusive calendar dates; ``keep`` is the
    number of final sessions to keep (5 for the "5d" range), else ``None``.
    """
    today = today or dt.datetime.now(dt.timezone.utc).date()
    if "period1" in params:
        def utc_date(seconds):
            return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).date()
        # build_params pads period2 by a day so the final session is inclusive.
        return utc_date(params["period1"]), utc_date(params["period2"] - SECONDS_PER_DAY), None
    range_ = params.get("range")
    if range_ == "5d":
        return today - dt.timedelta(days=FIVE_DAY_LOOKBACK), today, 5
    if range_ == "ytd":
        return dt.date(today.year, 1, 1), today, None
    if range_ == "max":
        return EARLIEST, today, None
    if range_ in RANGE_DAYS:
        return today - dt.timedelta(days=RANGE_DAYS[range_]), today, None
    raise ValueError(f"unsupported range {range_!r}")


def aggregate(rows, interval):
    """Daily ``rows`` as ``interval`` bars: "1d" (unchanged), "1wk" or "1mo".

    A weekly bar is dated the Monday of its week and a monthly bar the 1st of
    its month, as Yahoo dates them. Open is the first open, high / low the
    extremes, close and adjusted close the last ones, volume the sum.
    """
    if interval == "1d":
        return rows
    if interval not in ("1wk", "1mo"):
        raise ValueError(f"unsupported interval {interval!r}")

    def period_start(date_text):
        date = dt.date.fromisoformat(date_text)
        if interval == "1wk":
            return date - dt.timedelta(days=date.weekday())
        return date.replace(day=1)

    groups = {}
    for row in rows:
        groups.setdefault(period_start(row["date"]), []).append(row)

    def values(group, key):
        return [r[key] for r in group if r[key] is not None]

    bars = []
    for start, group in groups.items():
        opens, highs, lows = values(group, "open"), values(group, "high"), values(group, "low")
        volumes = values(group, "volume")
        bars.append({
            "date": start.isoformat(),
            "open": opens[0] if opens else None,
            "high": max(highs) if highs else None,
            "low": min(lows) if lows else None,
            "close": group[-1]["close"],
            "adj_close": group[-1]["adj_close"],
            "volume": sum(volumes) if volumes else None,
        })
    return bars


def _api_key(provider):
    name, script = KEYS[provider]
    load_dotenv()
    key = os.environ.get(name)
    if not key:
        raise ValueError(f"{name} must be set (see the module docstring in {script})")
    return key


def fetch_daily(provider, provider_symbol, first, final, api_key):
    """Return ``(rows, notes)``: the provider's daily rows from ``first`` on, oldest first."""
    if provider == "eodhd":
        payload = eodph.fetch_eod(provider_symbol, first, final, api_key)
        return eodph.extract_rows(payload)
    global _last_alphavantage_call
    wait = ALPHAVANTAGE_MIN_GAP - (time.monotonic() - _last_alphavantage_call)
    if wait > 0:
        time.sleep(wait)
    try:
        payload = avph.fetch_daily(provider_symbol, api_key)
    finally:
        _last_alphavantage_call = time.monotonic()
    rows = avph.extract_rows(payload)
    note = avph.history_note(rows, first, False)
    return rows, [note] if note else []


def daily_history(symbol, params):
    """Return stock_data.daily_history()'s shape for the Yahoo ticker
    ``symbol`` over the yahoo_finance.build_params() window ``params``.

    Raises ``ValueError`` for a ticker no source covers, a missing key, or an
    unsupported window, and ``requests.RequestException`` (key redacted, the
    provider named) when the provider fails or refuses.
    """
    provider, provider_symbol, exchange, currency = route(symbol)
    first, final, keep = window(params)
    interval = params.get("interval", "1d")
    api_key = _api_key(provider)
    source = PROVIDERS[provider]

    try:
        rows, notes = fetch_daily(provider, provider_symbol, first, final, api_key)
    except (requests.RequestException, ValueError) as exc:
        message = str(exc).replace(api_key, "<redacted>")
        raise requests.RequestException(f"{source} ({provider_symbol}): {message}") from None

    rows = daily_prices.in_window(rows, first, final)
    if keep:
        rows = rows[-keep:]
    return {
        "source": source,
        "notes": notes,
        "symbol": symbol,
        "exchange": exchange,
        "currency": currency,
        "bars": aggregate(rows, interval),
    }
