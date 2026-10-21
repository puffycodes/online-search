#!/usr/bin/env python3
"""
Pull the past daily open / high / low / close prices of a stock from Alpha
Vantage's TIME_SERIES_DAILY API:
https://www.alphavantage.co/documentation/#daily

Requires an ALPHAVANTAGE_API_KEY, set as an environment variable or in a .env
file at the repo root. Get one at https://www.alphavantage.co/support/#api-key
(free tier: 25 requests/day, and only the latest 100 sessions per symbol;
--full, the whole 20+ year history, needs a premium key). Real environment
variables always take precedence over .env values.

Give it a ticker in Alpha Vantage's notation: AAPL, TSCO.LON, MBG.DEX,
MC.PAR, SHOP.TRT, RELIANCE.BSE (India's Bombay exchange). Singapore, Tokyo
and Hong Kong listings weren't found when tested (docs/things-to-explore.md).
TIME_SERIES_DAILY prices are as traded; it has no adjusted close (that is the
premium TIME_SERIES_DAILY_ADJUSTED), so adj_close is always null.

Supports --json for structured output so an agent can parse stdout instead
of the human-readable report. On failure the process exits non-zero and
prints {"error": "..."} to stderr.
"""

import argparse
import json

import requests

import daily_prices
from cli_utils import die, load_dotenv, require_env, use_utf8_output

QUERY_URL = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT = 15
SOURCE = "Alpha Vantage"
SERIES_KEY = "Time Series (Daily)"
# Sessions returned by outputsize=compact, the only size free keys get.
COMPACT_SESSIONS = 100
# Keys Alpha Vantage uses for a refusal sent as HTTP 200: an unknown symbol
# ("Error Message"), a premium-only request or the daily limit
# ("Information"), and the older rate-limit wording ("Note").
MESSAGE_KEYS = ("Error Message", "Information", "Note")


def fetch_daily(symbol, api_key, full=False):
    """Return Alpha Vantage's TIME_SERIES_DAILY payload for ``symbol``.

    ``full`` asks for the whole history (premium keys only); otherwise the
    latest COMPACT_SESSIONS sessions come back. Raises ``ValueError`` carrying
    Alpha Vantage's message when it refuses, or when the body is empty (which
    has been seen under rate limiting), and ``requests.RequestException`` for
    a network failure.
    """
    resp = requests.get(
        QUERY_URL,
        params={
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "full" if full else "compact",
            "apikey": api_key,
        },
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise ValueError(f"HTTP {resp.status_code}: {resp.reason}")
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected response: {str(payload)[:200]}")
    for key in MESSAGE_KEYS:
        if payload.get(key):
            raise ValueError(str(payload[key]))
    if not payload:
        raise ValueError("empty response (possibly the rate limit)")
    if not isinstance(payload.get(SERIES_KEY), dict):
        raise ValueError(f"no {SERIES_KEY!r} in the response")
    return payload


def extract_rows(payload):
    """Return the rows of a TIME_SERIES_DAILY payload, oldest first.

    Alpha Vantage sends every value as a string under keys like "1. open";
    sessions without a close are skipped. Its "Meta Data" time zone is left
    out: it said "US/Eastern" even for RELIANCE.BSE.
    """
    rows = []
    for date, bar in payload[SERIES_KEY].items():
        if bar.get("4. close") in (None, ""):
            continue
        rows.append(
            daily_prices.price_row(
                date, bar.get("1. open"), bar.get("2. high"), bar.get("3. low"),
                bar["4. close"], None, bar.get("5. volume"),
            )
        )
    rows.sort(key=lambda row: row["date"])
    return rows


def history_note(rows, first, full):
    """A note when a compact answer can't reach back to ``first``, else ``None``."""
    if full or len(rows) < COMPACT_SESSIONS or first.isoformat() >= rows[0]["date"]:
        return None
    return (
        f"Only the latest {COMPACT_SESSIONS} sessions are available (from "
        f"{rows[0]['date']}); the full history (--full) needs a premium key."
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Pull past daily open/high/low/close prices from Alpha Vantage."
    )
    parser.add_argument(
        "symbol",
        help="Ticker in Alpha Vantage notation, e.g. AAPL, TSCO.LON, RELIANCE.BSE",
    )
    daily_prices.add_window_args(parser, "Return only the most recent N trading sessions")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Fetch the whole history instead of the latest 100 sessions (premium keys only).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    try:
        first, final = daily_prices.resolve_window(args.start, args.end, args.last)
    except ValueError as exc:
        die(str(exc), args.json)

    load_dotenv()
    api_key = require_env("ALPHAVANTAGE_API_KEY", "alphavantage_price_history.py", args.json)

    try:
        payload = fetch_daily(args.symbol, api_key, args.full)
        all_rows = extract_rows(payload)
    except (requests.RequestException, ValueError) as exc:
        # A network error's message can include the request URL, key and all.
        message = str(exc).replace(api_key, "<redacted>")
        die(f"failed to fetch prices for {args.symbol!r}: {message}", args.json)

    note = history_note(all_rows, first, args.full)
    notes = [note] if note else []
    rows = daily_prices.in_window(all_rows, first, final)
    if args.last:
        rows = rows[-args.last:]

    if args.json:
        print(
            json.dumps(
                {
                    "symbol": args.symbol,
                    "source": SOURCE,
                    "notes": notes,
                    "prices": rows,
                },
                indent=2,
            )
        )
        return

    for note in notes:
        print(f"Note: {note}")
    if not rows:
        print(f"No settled price data found for {args.symbol}.")
        return
    if notes:
        print()
    daily_prices.print_table(f"{args.symbol} - {SOURCE}", rows)


if __name__ == "__main__":
    main()
