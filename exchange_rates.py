#!/usr/bin/env python3
"""
Look up exchange rates from Frankfurter: https://frankfurter.dev/

Frankfurter blends the reference rates of about 106 central banks and other
official sources (the ECB among them) into one daily rate per currency pair,
for about 228 currencies, back to 1948. It is free, keyless and has no quotas;
its blended rates are "free to use" (docs/source-audit.md). This script asks
only for the blended rates, never a single provider's, which would fall under
that provider's own terms.

Give it a base currency and, optionally, the quote currencies to convert into
(all of them by default), as ISO codes such as USD, EUR, SGD or JPY. It
returns the latest rates, the rates on one date (--date), or the daily rates
over a range (--start / --end), optionally one per week or month (--group).
--amount converts an amount of the base currency as well.

Supports --json for structured output so an agent can parse stdout instead
of the human-readable report. On failure the process exits non-zero and
prints {"error": "..."} to stderr.
"""

import argparse
import json
import math

import requests

import daily_prices
from cli_utils import die, raise_for_status, use_utf8_output

RATES_URL = "https://api.frankfurter.dev/v2/rates"
REQUEST_TIMEOUT = 15
SOURCE = "Frankfurter (frankfurter.dev): blended rates from central banks and official sources"


def positive_float(value):
    """argparse ``type`` for a number greater than 0."""
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid number: {value!r}")
    if not number > 0:
        raise argparse.ArgumentTypeError(f"must be greater than 0, got {value}")
    return number


def build_params(base, quotes=None, date=None, start=None, end=None, group=None):
    """Frankfurter's query parameters for one request.

    ``date`` asks for one day, ``start`` / ``end`` for a range (``group`` of
    "week" or "month" thins a range to one rate per period); neither asks for
    the latest rates. No ``quotes`` means every currency.
    """
    params = {"base": base}
    if quotes:
        params["quotes"] = ",".join(quotes)
    if date:
        params["date"] = date.isoformat()
    if start:
        params["from"] = start.isoformat()
        params["to"] = end.isoformat()
        if group:
            params["group"] = group
    return params


def fetch_rates(params):
    """Return Frankfurter's list of ``{date, base, quote, rate}`` records.

    Raises ``requests.HTTPError`` carrying Frankfurter's message for a failed
    request (an unknown currency is a 422 "invalid currency: XXX"),
    ``ValueError`` for a body that isn't a JSON list, and
    ``requests.RequestException`` for a network failure.
    """
    resp = requests.get(RATES_URL, params=params, timeout=REQUEST_TIMEOUT)
    raise_for_status(resp)
    payload = resp.json()
    if not isinstance(payload, list):
        raise ValueError(f"unexpected response: {str(payload)[:200]}")
    return payload


def rate_rows(payload, amount=1.0):
    """Return ``[{date, quote, rate, converted}]``, sorted by date then quote.

    ``converted`` is ``amount`` of the base currency in the quote currency,
    to 10 significant digits (clearing float noise such as 319.37499999999994
    while keeping a tiny rate's digits, USD to BTC being about 0.00001). Records
    without a date, quote or rate are skipped.
    """
    rows = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        date, quote, rate = record.get("date"), record.get("quote"), record.get("rate")
        if not date or not quote or rate is None:
            continue
        rows.append({
            "date": date,
            "quote": quote,
            "rate": rate,
            "converted": float(f"{amount * rate:.10g}"),
        })
    rows.sort(key=lambda row: (row["date"], row["quote"]))
    return rows


def describe_window(args):
    """The window in words, for the report heading and the no-data message."""
    if args.date:
        return f"on {args.date}"
    if args.start:
        period = f" (one rate per {args.group})" if args.group else ""
        return f"from {args.start} to {args.end}{period}"
    return "latest"


def amount_text(value):
    """``value`` with thousands separators, and no decimals when it is whole."""
    return f"{value:,.0f}" if value == int(value) else f"{value:,.4f}".rstrip("0")


def number_text(value):
    """``value`` to 4 dp, or to 4 significant digits when it is below 0.01
    (USD to BTC is about 0.00001)."""
    if value and abs(value) < 0.01:
        decimals = 3 - math.floor(math.log10(abs(value)))
        return f"{value:.{decimals}f}"
    return f"{value:,.4f}"


def print_single(rows, base, amount):
    """One line per quote currency, in code order, with its own date (the
    latest rates of different currencies can come from different days)."""
    for row in sorted(rows, key=lambda row: row["quote"]):
        line = f"{row['date']}  {amount_text(amount)} {base} = {number_text(row['converted'])} {row['quote']}"
        if amount != 1:
            line += f"  (rate {row['rate']:.12f}".rstrip("0").rstrip(".") + ")"
        print(line)


def print_series(rows):
    """A date-by-quote table of the converted amounts."""
    quotes = sorted({row["quote"] for row in rows})
    by_date = {}
    for row in rows:
        by_date.setdefault(row["date"], {})[row["quote"]] = row["converted"]
    header = f"{'Date':<12}" + "".join(f"{quote:>14}" for quote in quotes)
    print(header)
    print("-" * len(header))
    for date in sorted(by_date):
        cells = by_date[date]
        print(f"{date:<12}" + "".join(
            f"{number_text(cells[q]):>14}" if q in cells else f"{'-':>14}" for q in quotes
        ))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Look up exchange rates from Frankfurter.")
    parser.add_argument("base", help="Base currency, an ISO code such as USD, EUR or SGD")
    parser.add_argument(
        "quotes", nargs="*", metavar="QUOTE",
        help="Currencies to convert into (default: every currency Frankfurter has)",
    )
    parser.add_argument(
        "--amount", type=positive_float, default=1.0,
        help="Amount of the base currency to convert (default: 1)",
    )
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--date", help="Rates on one date, YYYY-MM-DD")
    window.add_argument("--start", help="Start of a date range, YYYY-MM-DD (with optional --end)")
    parser.add_argument("--end", help="End of the date range, YYYY-MM-DD (defaults to today)")
    parser.add_argument(
        "--group", choices=("week", "month"),
        help="With --start: one rate per week or month instead of per day",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON on stdout instead of a human-readable report.",
    )
    args = parser.parse_args(argv)
    if args.group and not args.start:
        parser.error("--group requires --start")
    if args.end and args.date:
        parser.error("--end can't be used with --date")
    return args


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)
    base = args.base.upper()
    quotes = [quote.upper() for quote in args.quotes]

    date = start = end = None
    try:
        if args.date:
            date = daily_prices.parse_date(args.date)
        elif args.start or args.end:
            start, end = daily_prices.resolve_window(args.start, args.end)
            args.start, args.end = start.isoformat(), end.isoformat()
    except ValueError as exc:
        die(str(exc), args.json)

    params = build_params(base, quotes, date, start, end, args.group)
    try:
        rows = rate_rows(fetch_rates(params), args.amount)
    except (requests.RequestException, ValueError) as exc:
        die(f"failed to fetch exchange rates for {base}: {exc}", args.json)

    if args.json:
        print(json.dumps({
            "base": base,
            "quotes": quotes,
            "amount": args.amount,
            "date": args.date,
            "start": args.start,
            "end": args.end,
            "group": args.group,
            "source": SOURCE,
            "rates": rows,
        }, indent=2, ensure_ascii=False))
        return

    window = describe_window(args)
    if not rows:
        targets = ", ".join(quotes) if quotes else "any currency"
        print(f"No {base} rates found for {targets} {window}.")
        print(f"\nSource: {SOURCE}")
        return

    print(f"{base} exchange rates - {window}\n")
    if start:
        print(f"{amount_text(args.amount)} {base} in each currency:\n")
        print_series(rows)
    else:
        print_single(rows, base, args.amount)
    print(f"\nSource: {SOURCE}")


if __name__ == "__main__":
    main()
