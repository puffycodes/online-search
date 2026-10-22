#!/usr/bin/env python3
"""
Describe how risky one or more instruments' recent prices have been -
volatility, the worst peak-to-trough drawdown, and how closely each pair
moved together - using daily prices from EODHD or Alpha Vantage through
stock_data.daily_history() (served by price_source.py, which needs
EODHD_API_KEY and, for India, ALPHAVANTAGE_API_KEY).

Give it one or more tickers in Yahoo notation (AAPL, VOD.L, RELIANCE.NS,
^GSPC, EURUSD=X, BTC-USD, ...; not Singapore .SI, Tokyo .T or futures =F for
now) and either a --range keyword, an explicit
--start/--end window, or --last N to use just the most recent N sessions.
--benchmark SYMBOL (e.g. ^GSPC) adds one more series to read the others
against: it gets the same figures and joins every correlation pair.

Prices are the adjusted close (splits and dividends folded in) when the
source supplies it for every session, otherwise the raw close, so a split doesn't
read as a crash. Volatility is annualized over 365 sessions a year for a
series that trades at weekends (crypto) and 252 otherwise. Each correlation
uses only the dates both series traded. All figures come from
indicators.py's volatility(), max_drawdown() and correlation(), and describe
the window measured - not what comes next.

A symbol that fails to fetch or has no settled prices is skipped and listed
under "skipped"; the run fails only when every symbol does.

Supports --json for structured output so an agent can parse stdout instead
of the human-readable report. On failure the process exits non-zero and
prints {"error": "..."} to stderr.
"""

import argparse
import datetime as dt
import itertools
import json
import sys

import requests

import stock_data
import yahoo_finance as yf
from cli_utils import die, use_utf8_output
from indicators import correlation, max_drawdown, volatility

DEFAULT_RANGE = "1y"
TRADING_DAYS_PER_YEAR = 252
CALENDAR_DAYS_PER_YEAR = 365


def extract_closes(history):
    """Return (rows, basis) from stock_data.daily_history()'s ``history``.

    rows is a list of (date, price) pairs, oldest first, skipping sessions
    with no close. basis is "adj_close" when every kept session has an
    adjusted close (and prices are those), otherwise "close".
    """
    kept = []
    for bar in history["bars"]:
        if bar["close"] is None:
            # In-progress session or a data gap - not a settled close.
            continue
        kept.append((dt.date.fromisoformat(bar["date"]), bar["close"], bar["adj_close"]))
    use_adj = bool(kept) and all(adj is not None for _, _, adj in kept)
    rows = [(date, adj if use_adj else close) for date, close, adj in kept]
    return rows, "adj_close" if use_adj else "close"


def periods_per_year(dates):
    """Sessions in a year for this series: 365 if it trades at weekends, else 252."""
    if any(date.weekday() >= 5 for date in dates):
        return CALENDAR_DAYS_PER_YEAR
    return TRADING_DAYS_PER_YEAR


def summarize(symbol, history, rows, basis):
    """The per-symbol risk figures as a JSON-ready dict."""
    dates = [d for d, _ in rows]
    prices = [p for _, p in rows]
    per_year = periods_per_year(dates)

    def iso(index):
        return dates[index].isoformat() if index is not None else None

    def price_at(index):
        return round(prices[index], 4) if index is not None else None

    dd = max_drawdown(prices)
    high_index = prices.index(max(prices))
    symbol, exchange, currency = stock_data.label(history, symbol)
    return {
        "symbol": symbol,
        "exchange": exchange,
        "currency": currency,
        "source": history["source"],
        "notes": history["notes"] or [],
        "basis": basis,
        "sessions": len(prices),
        "start": iso(0),
        "end": iso(len(prices) - 1),
        "first": price_at(0),
        "last": price_at(len(prices) - 1),
        "change": prices[-1] / prices[0] - 1,
        "periods_per_year": per_year,
        "volatility": volatility(prices, per_year) if len(prices) >= 3 else None,
        "max_drawdown": {
            "drawdown": dd["drawdown"],
            "peak_date": iso(dd["peak"]),
            "peak": price_at(dd["peak"]),
            "trough_date": iso(dd["trough"]),
            "trough": price_at(dd["trough"]),
            "recovery_date": iso(dd["recovery"]),
        },
        "high_date": iso(high_index),
        "high": price_at(high_index),
        "from_high": prices[-1] / prices[high_index] - 1,
    }


def pair_correlation(name_a, rows_a, name_b, rows_b):
    """Correlation of two series over the dates both traded, as a JSON-ready dict."""
    prices_b = dict(rows_b)
    shared = [(d, p, prices_b[d]) for d, p in rows_a if d in prices_b]
    value = None
    if len(shared) >= 3:
        value = correlation([p for _, p, _ in shared], [q for _, _, q in shared])
    return {
        "a": name_a,
        "b": name_b,
        "sessions": len(shared),
        "start": shared[0][0].isoformat() if shared else None,
        "end": shared[-1][0].isoformat() if shared else None,
        "correlation": value,
    }


def load_symbol(symbol, params, last):
    """(history, rows, basis) for symbol, or a skip reason string on failure."""
    try:
        history = stock_data.daily_history(symbol, params)
        rows, basis = extract_closes(history)
    except (requests.RequestException, ValueError, KeyError) as exc:
        return f"failed to fetch prices: {exc}"
    if last:
        rows = rows[-last:]
    if not rows:
        return "no settled price data in the window"
    if any(price <= 0 for _, price in rows):
        return "non-positive prices in the window"
    return history, rows, basis


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Describe the volatility, worst drawdown and correlation "
                    "of one or more stocks' recent prices.",
    )
    parser.add_argument(
        "symbols",
        nargs="+",
        help="Tickers in Yahoo notation, e.g. AAPL VOD.L RELIANCE.NS BTC-USD",
    )
    yf.add_window_args(parser, DEFAULT_RANGE, "Use only the most recent N sessions")
    parser.add_argument(
        "--benchmark",
        metavar="SYMBOL",
        help="Also measure this symbol (e.g. ^GSPC) and correlate every "
             "other symbol with it",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON on stdout instead of a human-readable report.",
    )
    args = parser.parse_args(argv)
    # Drop repeats (case-insensitively), and a benchmark also listed as a
    # symbol, which is measured once, as the benchmark.
    seen = {args.benchmark.upper()} if args.benchmark else set()
    symbols = []
    for symbol in args.symbols:
        if symbol.upper() not in seen:
            seen.add(symbol.upper())
            symbols.append(symbol)
    if not symbols:
        parser.error("give at least one symbol besides the --benchmark")
    args.symbols = symbols
    return args


def pct(value, signed=True):
    if value is None:
        return "-"
    return f"{value:+.1%}" if signed else f"{value:.1%}"


def print_report(payload):
    for entry in payload["skipped"]:
        print(f"Warning: skipped {entry['symbol']!r}: {entry['reason']}", file=sys.stderr)

    rows = payload["symbols"] + ([payload["benchmark"]] if payload["benchmark"] else [])
    for row in rows:
        label = row["symbol"] + (" (benchmark)" if row is payload["benchmark"] else "")
        dd = row["max_drawdown"]
        print(f"{label} - {row['exchange']} ({row['currency']}) - {row['source']}")
        for note in row["notes"]:
            print(f"  note        : {note}")
        print(f"  {row['sessions']} session(s), {row['start']} -> {row['end']}"
              f"  [{row['basis']}, {row['periods_per_year']} sessions/year]")
        print(f"  change      : {pct(row['change'])}  "
              f"({row['first']:,.4f} -> {row['last']:,.4f})")
        print(f"  volatility  : {pct(row['volatility'], signed=False)} a year"
              if row["volatility"] is not None else
              "  volatility  : - (needs at least 3 sessions)")
        if dd["peak_date"] is None:
            print("  worst fall  : none (never closed below an earlier high)")
        else:
            recovered = dd["recovery_date"] or "not yet"
            print(f"  worst fall  : {pct(dd['drawdown'])}  "
                  f"{dd['peak_date']} ({dd['peak']:,.4f}) -> "
                  f"{dd['trough_date']} ({dd['trough']:,.4f}), recovered {recovered}")
        print(f"  from high   : {pct(row['from_high'])}  "
              f"(high {row['high']:,.4f} on {row['high_date']})")
        print()

    if payload["correlations"]:
        print("Correlation of daily returns (shared sessions only)")
        width = max(len(f"{p['a']} / {p['b']}") for p in payload["correlations"])
        for pair in payload["correlations"]:
            name = f"{pair['a']} / {pair['b']}"
            value = (f"{pair['correlation']:+.2f}" if pair["correlation"] is not None
                     else "  - ")
            print(f"  {name:<{width}}  {value}  ({pair['sessions']} sessions)")
        print()

    print("Describes the window measured; past swings and falls don't predict future ones.")


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    try:
        params = yf.build_params(
            range_=args.range, start=args.start, end=args.end, last=args.last,
        )
    except ValueError as exc:
        die(str(exc), args.json)

    if not args.json:
        names = ", ".join(args.symbols + ([args.benchmark] if args.benchmark else []))
        print(f"Measuring risk for {names}...\n")

    loaded, skipped = {}, []
    for symbol in args.symbols + ([args.benchmark] if args.benchmark else []):
        outcome = load_symbol(symbol, params, args.last)
        if isinstance(outcome, str):
            skipped.append({"symbol": symbol, "reason": outcome})
        else:
            loaded[symbol] = outcome

    if not any(symbol in loaded for symbol in args.symbols):
        reasons = "; ".join(f"{s['symbol']}: {s['reason']}" for s in skipped)
        die(f"no price data for any symbol ({reasons})", args.json)

    summaries = {symbol: summarize(symbol, *outcome) for symbol, outcome in loaded.items()}
    names = {symbol: summaries[symbol]["symbol"] for symbol in loaded}
    correlations = [
        pair_correlation(names[a], loaded[a][1], names[b], loaded[b][1])
        for a, b in itertools.combinations(loaded, 2)
    ]

    payload = {
        "symbols": [summaries[s] for s in args.symbols if s in summaries],
        "benchmark": summaries.get(args.benchmark) if args.benchmark else None,
        "correlations": correlations,
        "skipped": skipped,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return
    print_report(payload)


if __name__ == "__main__":
    main()
