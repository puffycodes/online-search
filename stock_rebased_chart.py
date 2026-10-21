#!/usr/bin/env python3
"""
Fetch closing-price history for a series of symbols from EODHD or Alpha
Vantage through price_source.py (which needs EODHD_API_KEY and, for India,
ALPHAVANTAGE_API_KEY), rebase each to 100 as of a common reference date, and
plot the rebased series together with matplotlib.

Give it one or more tickers in Yahoo's notation (AAPL, VOD.L, SAP.DE,
RELIANCE.NS, ...; not Singapore .SI, Tokyo .T or futures =F for now) and either a --range keyword, an explicit --start/--end window,
or --last N to fetch just the most recent N sessions. Pick the reference
date with --base-date (YYYY-MM-DD); by default it is the first date in the
first symbol's price series.

Each symbol's close-price series is rescaled with indicators.rebase() so its
value on the reference date reads as 100 - values above 100 mean the stock
has risen relative to that date, below 100 means it has fallen. A symbol
with no settled close on the reference date is dropped with a warning.

--benchmark SYMBOL (e.g. ^GSPC) adds one more series, rebased the same way
but drawn as a heavier black dashed line so the stocks can be read against
it. It never sets the default reference date, and if it cannot be drawn the
chart is still made without it.

By default the chart is written to rebased_chart.png; use --output to
change the path or --show to open an interactive window instead.

On failure the process exits non-zero and prints an error to stderr.
"""

import argparse
import sys

import requests

import price_source
import yahoo_finance as yf
from cli_utils import die, use_utf8_output
from indicators import rebase

DEFAULT_RANGE = "6mo"
DEFAULT_OUTPUT = "rebased_chart.png"

# Cycled if there are more symbols than colours.
COLOR_LINES = [
    "#1f78b4", "#e6550d", "#33a02c", "#e31a1c",
    "#6a3d9a", "#a6761d", "#e7298a", "#555555",
]
# The benchmark line: black, dashed and heavier, so it never looks like a stock.
BENCHMARK_COLOR = "#000000"


def fetch_closes(symbol, params):
    """Return a list of (date, close) pairs for symbol, oldest first."""
    result = price_source.fetch_history(symbol, params)
    meta, series = yf.extract_series(result)
    for note in meta.get("notes") or []:
        print(f"Note: {symbol}: {note}", file=sys.stderr)
    gmtoffset = series["gmtoffset"]
    rows = []
    for ts, close in zip(series["timestamp"], series["close"]):
        if close is None:
            # In-progress session or a data gap - not a settled close.
            continue
        date = yf.session_datetime(ts, gmtoffset).date()
        rows.append((date, close))
    return meta, rows


def render_chart(series, base_date, out_path, show, benchmark=None):
    """Plot each (symbol, dates, values) in series, plus an optional benchmark."""
    import matplotlib

    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)

    for idx, (symbol, dates, values) in enumerate(series):
        color = COLOR_LINES[idx % len(COLOR_LINES)]
        ax.plot(dates, values, color=color, linewidth=1.5, label=symbol)

    if benchmark is not None:
        symbol, dates, values = benchmark
        ax.plot(dates, values, color=BENCHMARK_COLOR, linewidth=2.2, linestyle="--",
                label=f"{symbol} (benchmark)", zorder=1.5)

    ax.axhline(100, color="#999999", linewidth=0.8, linestyle="--", zorder=1)
    ax.grid(True, color="#d0d0d0", linewidth=0.5, alpha=0.7)
    ax.set_axisbelow(True)
    ax.set_ylabel("Rebased price (base = 100)")
    ax.set_title(f"Rebased to {base_date:%Y-%m-%d}", fontsize=12, loc="left")
    for label in ax.get_xticklabels():
        label.set_rotation(45)
        label.set_horizontalalignment("right")
    ax.legend(loc="best", fontsize=9, framealpha=0.9)

    if show:
        plt.show()
    else:
        fig.savefig(out_path, dpi=150)
        print(f"Wrote {out_path}")
    plt.close(fig)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Rebase a series of stocks' closing prices to a common "
                     "date and plot them together (matplotlib).",
    )
    parser.add_argument(
        "symbols",
        nargs="+",
        help="Tickers in Yahoo notation, e.g. AAPL VOD.L D05.SI SAP.DE",
    )
    yf.add_window_args(parser, DEFAULT_RANGE, "Fetch only the most recent N sessions")
    parser.add_argument(
        "--base-date",
        help="Reference date YYYY-MM-DD that each series is rebased to read "
             "100 (default: the first date in the first symbol's series)",
    )
    parser.add_argument(
        "--benchmark",
        metavar="SYMBOL",
        help="Also draw this symbol (e.g. ^GSPC) as a dashed benchmark line "
             "to compare the others against",
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"PNG path to write (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open an interactive window instead of writing a file",
    )
    args = parser.parse_args(argv)
    if args.benchmark:
        # A benchmark also listed as a symbol is drawn once, as the benchmark.
        args.symbols = [s for s in args.symbols if s.upper() != args.benchmark.upper()]
        if not args.symbols:
            parser.error("give at least one symbol besides the --benchmark")
    return args


def load_closes(symbol, params, last):
    """(date, close) rows for symbol, or None with a warning if there are none."""
    try:
        _, rows = fetch_closes(symbol, params)
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"Warning: failed to fetch prices for {symbol!r}: {exc}", file=sys.stderr)
        return None
    if last:
        rows = rows[-last:]
    if not rows:
        print(f"Warning: no settled price data found for {symbol!r}", file=sys.stderr)
        return None
    return rows


def rebase_rows(symbol, rows, base_date):
    """(symbol, dates, values) rebased to 100 on base_date, or None with a warning."""
    dates = [d for d, _ in rows]
    closes = [c for _, c in rows]
    try:
        base_index = dates.index(base_date)
    except ValueError:
        print(
            f"Warning: {symbol!r} has no settled close on {base_date:%Y-%m-%d}, skipping",
            file=sys.stderr,
        )
        return None
    return symbol, dates, rebase(closes, base_index)


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    try:
        params = yf.build_params(
            range_=args.range, start=args.start, end=args.end, last=args.last,
        )
        base_date = yf.parse_date(args.base_date).date() if args.base_date else None
    except ValueError as exc:
        die(str(exc))

    fetched = {}
    for symbol in args.symbols:
        rows = load_closes(symbol, params, args.last)
        if rows is not None:
            fetched[symbol] = rows

    if not fetched:
        die("no price data found for any symbol")

    benchmark_rows = load_closes(args.benchmark, params, args.last) if args.benchmark else None

    if base_date is None:
        first_symbol = args.symbols[0]
        if first_symbol not in fetched:
            first_symbol = next(iter(fetched))
        base_date = fetched[first_symbol][0][0]

    series = []
    for symbol, rows in fetched.items():
        rebased = rebase_rows(symbol, rows, base_date)
        if rebased is not None:
            series.append(rebased)
    if not series:
        die(f"no symbol has a settled close on {base_date:%Y-%m-%d}")

    benchmark = None
    if benchmark_rows is not None:
        benchmark = rebase_rows(args.benchmark, benchmark_rows, base_date)

    try:
        render_chart(series, base_date, args.output, args.show, benchmark)
    except ImportError:
        die("matplotlib is required (pip install matplotlib)")


if __name__ == "__main__":
    main()
