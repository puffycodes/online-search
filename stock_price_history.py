#!/usr/bin/env python3
"""
Pull the past daily open / high / low / close prices of a single stock,
index, currency pair or crypto coin, from EODHD or Alpha Vantage through
stock_data.daily_history() (served by price_source.py, which needs
EODHD_API_KEY and, for India, ALPHAVANTAGE_API_KEY).

Give it a ticker in Yahoo's notation (AAPL, VOD.L, SAP.DE, RELIANCE.NS,
^GSPC, EURUSD=X, BTC-USD, ...) and either a --range keyword, an explicit
--start/--end window, or --last N to get just the most recent N sessions.
Singapore (.SI), Tokyo (.T) and futures (=F) aren't supported for now.

Supports --json for structured output so an agent can parse stdout instead
of the human-readable report. On failure the process exits non-zero and
prints {"error": "..."} to stderr.
"""

import argparse
import json

import requests

import stock_data
import yahoo_finance as yf
from cli_utils import die, use_utf8_output

DEFAULT_RANGE = "1mo"


def extract_rows(history):
    """The settled sessions of stock_data.daily_history()'s ``history``, as
    ``{date, open, high, low, close, adj_close, volume}`` rows rounded to 4
    places; a bar without a close (an in-progress session or a gap) is left out."""
    def at(value):
        return round(value, 4) if value is not None else None

    rows = []
    for bar in history["bars"]:
        if bar["close"] is None:
            continue
        rows.append(
            {
                "date": bar["date"],
                "open": at(bar["open"]),
                "high": at(bar["high"]),
                "low": at(bar["low"]),
                "close": round(bar["close"], 4),
                "adj_close": at(bar["adj_close"]),
                "volume": int(bar["volume"]) if bar["volume"] is not None else None,
            }
        )
    return rows


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Pull past daily open/high/low/close prices for a single stock."
    )
    parser.add_argument(
        "symbol",
        help="Ticker in Yahoo notation, e.g. AAPL, VOD.L, SAP.DE, RELIANCE.NS, ^GSPC",
    )
    yf.add_window_args(parser, DEFAULT_RANGE, "Return only the most recent N trading sessions")
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
        params = yf.build_params(
            range_=args.range, start=args.start, end=args.end, last=args.last
        )
        history = stock_data.daily_history(args.symbol, params)
        rows = extract_rows(history)
    except (requests.RequestException, ValueError, KeyError) as exc:
        die(f"failed to fetch prices for {args.symbol!r}: {exc}", args.json)

    if args.last:
        rows = rows[-args.last:]

    symbol, exchange, currency = stock_data.label(history, args.symbol)
    notes = history["notes"] or []

    if args.json:
        print(
            json.dumps(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "currency": currency,
                    "source": history["source"],
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
        print(f"No settled price data found for {symbol}.")
        return

    source = f" - {history['source']}" if history["source"] else ""
    print(f"{symbol} - {exchange} ({currency}){source} - {len(rows)} session(s)\n")
    show_adj = any(r["adj_close"] not in (None, r["close"]) for r in rows)

    def cell(value, width=12):
        return f"{value:>{width},.4f}" if value is not None else f"{'-':>{width}}"

    header = f"{'Date':<12}" + "".join(
        f"{name:>12}" for name in ("Open", "High", "Low", "Close")
    )
    if show_adj:
        header += f"{'Adj Close':>13}"
    header += f"{'Volume':>15}"
    print(header)
    print("-" * len(header))
    for row in rows:
        line = f"{row['date']:<12}" + cell(row["open"]) + cell(row["high"]) + \
            cell(row["low"]) + cell(row["close"])
        if show_adj:
            line += cell(row["adj_close"], 13)
        vol = row["volume"]
        line += f"{vol:>15,}" if vol is not None else f"{'-':>15}"
        print(line)

    latest = rows[-1]

    def num(value):
        return f"{value:,.4f}" if value is not None else "-"

    print(
        f"\nMost recent session ({latest['date']}): "
        f"O {num(latest['open'])}  H {num(latest['high'])}  "
        f"L {num(latest['low'])}  C {num(latest['close'])} {currency}"
    )


if __name__ == "__main__":
    main()
