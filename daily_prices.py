#!/usr/bin/env python3
"""
Shared helpers for the keyed daily-price scripts, eodhd_price_history.py and
alphavantage_price_history.py: the --start/--end/--last window flags and their
resolution to calendar dates, the {date, open, high, low, close, adj_close,
volume} row both scripts emit (the same row as stock_price_history.py), and
the text table both print. Each script keeps its own fetch and payload parsing.

Not a CLI itself - this module is imported, not run.
"""

import datetime as dt

from cli_utils import positive_int

# Calendar days looked back when no --start or --last is given (about a month,
# like stock_price_history.py's default "1mo" range).
DEFAULT_DAYS = 31


def parse_date(value):
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"invalid date {value!r}, expected YYYY-MM-DD")


def add_window_args(parser, last_help):
    """Add the --start / --end / --last window flags to an argparse ``parser``."""
    parser.add_argument("--start", help="Start date YYYY-MM-DD (with optional --end)")
    parser.add_argument("--end", help="End date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--last", type=positive_int, metavar="N", help=last_help)


def resolve_window(start=None, end=None, last=None, today=None):
    """Return the inclusive ``(first, final)`` calendar dates to keep.

    ``start`` (and ``end``, default today) wins. Otherwise ``last`` N sessions
    look back ``N*2 + 10`` calendar days, enough to cover weekends and holidays
    before the caller trims to N. Otherwise the window is DEFAULT_DAYS.
    Raises ``ValueError`` for a malformed date, ``end`` without ``start``, or
    an end before the start.
    """
    today = today or dt.date.today()
    if end and not start:
        raise ValueError("--end requires --start")
    if start:
        first = parse_date(start)
        final = parse_date(end) if end else today
        if final < first:
            raise ValueError(f"end date {final} is before start date {first}")
        return first, final
    days = last * 2 + 10 if last else DEFAULT_DAYS
    return today - dt.timedelta(days=days), today


def _number(value):
    if value in (None, ""):
        return None
    return round(float(value), 4)


def price_row(date, open_, high, low, close, adj_close, volume):
    """One session as ``{date, open, high, low, close, adj_close, volume}``.

    Prices are rounded to 4 dp and volume made an int; numeric strings (as
    Alpha Vantage sends) are accepted, and missing values become ``None``.
    """
    return {
        "date": date,
        "open": _number(open_),
        "high": _number(high),
        "low": _number(low),
        "close": _number(close),
        "adj_close": _number(adj_close),
        "volume": int(float(volume)) if volume not in (None, "") else None,
    }


def in_window(rows, first, final):
    """The ``rows`` dated from ``first`` to ``final`` inclusive."""
    first, final = first.isoformat(), final.isoformat()
    return [row for row in rows if first <= row["date"] <= final]


def print_table(title, rows, currency=""):
    """Print ``title``, a date / OHLC / (adj close) / volume table, and the
    most recent session's OHLC. The Adj Close column appears only when some
    adjusted close differs from its close."""
    print(f"{title} - {len(rows)} session(s)\n")
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

    suffix = f" {currency}" if currency else ""
    print(
        f"\nMost recent session ({latest['date']}): "
        f"O {num(latest['open'])}  H {num(latest['high'])}  "
        f"L {num(latest['low'])}  C {num(latest['close'])}{suffix}"
    )
