#!/usr/bin/env python3
"""
Pull the past daily open / high / low / close prices of a single stock,
using Yahoo Finance's public chart endpoint. No API key or authentication
required.

Give it a ticker in Yahoo's notation (AAPL, VOD.L, D05.SI, SAP.DE, ...) and
either a --range keyword, an explicit --start/--end window, or --last N to
get just the most recent N sessions.

Supports --json for structured output so an agent can parse stdout instead
of the human-readable report. On failure the process exits non-zero and
prints {"error": "..."} to stderr.
"""

import argparse
import datetime as dt
import json

import requests

import yahoo_finance as yf
from cli_utils import die, positive_int

DEFAULT_RANGE = "1mo"


def extract_rows(result):
    meta, series = yf.extract_series(result)
    gmtoffset = series["gmtoffset"]
    timestamps = series["timestamp"]
    opens = series["open"]
    highs = series["high"]
    lows = series["low"]
    closes = series["close"]
    volumes = series["volume"]
    adj_closes = series["adjclose"]

    def at(values, i):
        value = values[i] if i < len(values) else None
        return round(value, 4) if value is not None else None

    rows = []
    for i, ts in enumerate(timestamps):
        close = closes[i] if i < len(closes) else None
        if close is None:
            # In-progress session or a data gap - not a settled close.
            continue
        date = dt.datetime.utcfromtimestamp(ts + gmtoffset).strftime("%Y-%m-%d")
        volume = volumes[i] if i < len(volumes) else None
        rows.append(
            {
                "date": date,
                "open": at(opens, i),
                "high": at(highs, i),
                "low": at(lows, i),
                "close": round(close, 4),
                "adj_close": at(adj_closes or [], i),
                "volume": int(volume) if volume is not None else None,
            }
        )
    return meta, rows


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Pull past daily open/high/low/close prices for a single stock."
    )
    parser.add_argument(
        "symbol",
        help="Ticker in Yahoo notation, e.g. AAPL, VOD.L, D05.SI, SAP.DE",
    )
    window = parser.add_mutually_exclusive_group()
    window.add_argument(
        "--range",
        choices=yf.VALID_RANGES,
        default=DEFAULT_RANGE,
        help=f"Look-back window (default: {DEFAULT_RANGE})",
    )
    window.add_argument(
        "--last",
        type=positive_int,
        metavar="N",
        help="Return only the most recent N trading sessions",
    )
    parser.add_argument("--start", help="Start date YYYY-MM-DD (with optional --end)")
    parser.add_argument("--end", help="End date YYYY-MM-DD (defaults to today)")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        params = yf.build_params(
            range_=args.range, start=args.start, end=args.end, last=args.last
        )
        result = yf.fetch_history(args.symbol, params)
        meta, rows = extract_rows(result)
    except (requests.RequestException, ValueError, KeyError) as exc:
        die(f"failed to fetch prices for {args.symbol!r}: {exc}", args.json)

    if args.last:
        rows = rows[-args.last:]

    symbol, exchange, currency = yf.meta_summary(meta, args.symbol)

    if args.json:
        print(
            json.dumps(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "currency": currency,
                    "prices": rows,
                },
                indent=2,
            )
        )
        return

    if not rows:
        print(f"No settled price data found for {symbol}.")
        return

    print(f"{symbol} - {exchange} ({currency}) - {len(rows)} session(s)\n")
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
