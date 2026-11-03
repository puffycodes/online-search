#!/usr/bin/env python3
"""
Pull the past daily open / high / low / close prices of a stock, index,
currency pair or crypto coin from EODHD's end-of-day API:
https://eodhd.com/financial-apis/api-for-historical-data-and-volumes

Requires an EODHD_API_KEY, set as an environment variable or in a .env file
at the repo root. Get one by registering at https://eodhd.com/register (free
tier: 20 calls/day and one year of history; the "EOD Historical Data -
All World" plan lifts both). Real environment variables always take
precedence over .env values.

Give it a ticker in EODHD's notation, SYMBOL.EXCHANGE: AAPL.US, VOD.LSE,
SAP.XETRA, MC.PA, RY.TO, BHP.AU, 0700.HK, plus indices (GSPC.INDX), currency
pairs (EURUSD.FOREX) and crypto (BTC-USD.CC). Singapore, India and Tokyo
listings weren't found when tested (docs/things-to-explore.md).

Supports --json for structured output so an agent can parse stdout instead
of the human-readable report. On failure the process exits non-zero and
prints {"error": "..."} to stderr.
"""

import argparse
import json

import requests

import daily_prices
from cli_utils import die, load_dotenv, require_env, use_utf8_output

EOD_URL = "https://eodhd.com/api/eod/{symbol}"
REQUEST_TIMEOUT = 15
SOURCE = "EODHD"


def fetch_eod(symbol, first, final, api_key):
    """Return EODHD's list of daily bars for ``symbol`` from ``first`` to ``final``.

    Raises ``ValueError`` carrying EODHD's message for a non-200 answer (an
    unknown ticker is a 404 "Ticker Not Found.") or a body that isn't a JSON
    list, and ``requests.RequestException`` for a network failure.
    """
    resp = requests.get(
        EOD_URL.format(symbol=symbol),
        params={
            "api_token": api_key,
            "fmt": "json",
            "period": "d",
            "from": first.isoformat(),
            "to": final.isoformat(),
        },
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        message = resp.text.strip()[:200] or resp.reason
        raise ValueError(f"HTTP {resp.status_code}: {message}")
    payload = resp.json()
    if not isinstance(payload, list):
        raise ValueError(f"unexpected response: {str(payload)[:200]}")
    return payload


def extract_rows(payload):
    """Return ``(rows, notes)`` from EODHD's bar list, oldest first.

    Bars with no close are skipped. A ``warning`` on any bar becomes a note:
    the free plan answers a request older than a year with one recent bar
    carrying "Data is limited by one year as you have free subscription".
    """
    rows, notes = [], []
    for bar in payload:
        if not isinstance(bar, dict):
            continue
        warning = bar.get("warning")
        if warning and warning not in notes:
            notes.append(warning)
        if not bar.get("date") or bar.get("close") is None:
            continue
        rows.append(
            daily_prices.price_row(
                bar["date"], bar.get("open"), bar.get("high"), bar.get("low"),
                bar["close"], bar.get("adjusted_close"), bar.get("volume"),
            )
        )
    rows.sort(key=lambda row: row["date"])
    return rows, notes


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Pull past daily open/high/low/close prices from EODHD."
    )
    parser.add_argument(
        "symbol",
        help="Ticker in EODHD notation, e.g. AAPL.US, VOD.LSE, 0700.HK, GSPC.INDX",
    )
    daily_prices.add_window_args(parser, "Return only the most recent N trading sessions")
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
    api_key = require_env("EODHD_API_KEY", "eodhd_price_history.py", args.json)

    try:
        payload = fetch_eod(args.symbol, first, final, api_key)
        rows, notes = extract_rows(payload)
    except (requests.RequestException, ValueError) as exc:
        # A network error's message can include the request URL, key and all.
        message = str(exc).replace(api_key, "<redacted>")
        die(f"failed to fetch prices for {args.symbol!r}: {message}", args.json)

    # The free plan can return a bar outside the window; keep only the window.
    rows = daily_prices.in_window(rows, first, final)
    if args.last:
        rows = rows[-args.last:]

    if args.json:
        print(
            json.dumps(
                {"symbol": args.symbol, "source": SOURCE, "notes": notes, "prices": rows},
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
