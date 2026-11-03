#!/usr/bin/env python3
"""
Retrieve a stock's earnings calendar through stock_data.earnings_view(),
which serves it from Yahoo Finance's public ``quoteSummary`` endpoint today.
No API key or authentication required (yahoo_finance.py fetches a cookie +
crumb automatically).

Give it a ticker in Yahoo's notation (AAPL, VOD.L, D05.SI, SAP.DE, ...). The
script reports:

- next earnings     the announcement date/time (or Yahoo's estimated date
                    range), with the analyst EPS and revenue estimates for it
- dividend dates    the ex-dividend and payment dates Yahoo holds, and the
                    last dividend paid per share
- earnings history  the last four quarters' EPS: estimate, actual, surprise

Each date is flagged "upcoming" or "past" against today, because Yahoo keeps
showing the most recent dividend dates until the next ones are announced.
Only company stocks have earnings; an ETF, index, currency or future fails
with "no earnings data". Supports --json for structured output. On failure
the process exits non-zero and prints {"error": "..."} to stderr.
"""

import argparse
import datetime as dt
import json

import requests

import stock_data
from cli_utils import die, use_utf8_output
from stock_intrinsic_value import _fmt_big, _fmt_money


# --------------------------------------------------------------------------- #
# Shape                                                                        #
# --------------------------------------------------------------------------- #
def _status(date_str, today):
    if date_str is None:
        return None
    return "upcoming" if date_str >= today.isoformat() else "past"


def extract_calendar(view, today=None):
    """Turn stock_data.earnings_view()'s ``view`` into the JSON-shaped calendar dict.

    Each date gains an "upcoming" / "past" status against ``today`` (a
    ``date``; default today in UTC), and the reporting currency falls back to
    the trading currency.
    """
    today = today or dt.datetime.now(dt.timezone.utc).date()
    nxt = view["next_earnings"]
    if nxt is not None:
        nxt = {
            "date": nxt["date"],
            "date_end": nxt["date_end"],
            "datetime_utc": nxt["datetime_utc"],
            "is_estimate": nxt["is_estimate"],
            "status": _status(nxt["date"], today),
            "eps_estimate": nxt["eps_estimate"],
            "revenue_estimate": nxt["revenue_estimate"],
        }
    div = view["dividend"]
    if div is not None:
        div = {
            "ex_dividend_date": div["ex_dividend_date"],
            "ex_dividend_status": _status(div["ex_dividend_date"], today),
            "payment_date": div["payment_date"],
            "payment_status": _status(div["payment_date"], today),
            "last_amount": div["last_amount"],
            "last_amount_date": div["last_amount_date"],
            "amount_currency": div["amount_currency"],
        }
    return {
        "name": view["name"],
        "exchange": view["exchange"],
        "currency": view["currency"],
        "reporting_currency": view["reporting_currency"] or view["currency"],
        "next_earnings": nxt,
        "dividend": div,
        "earnings_history": view["earnings_history"],
    }


# --------------------------------------------------------------------------- #
# Output                                                                       #
# --------------------------------------------------------------------------- #
def _fmt_signed_pct(value):
    return "-" if value is None else f"{value * 100:+.2f}%"


def _fmt_range(estimate, fmt):
    if not estimate:
        return "-"
    text = fmt(estimate["average"])
    if estimate["low"] is not None and estimate["high"] is not None:
        text += f"  (range {fmt(estimate['low'])} - {fmt(estimate['high'])})"
    return text


def build_report(symbol, calendar):
    lines = []
    head = symbol
    if calendar["name"]:
        head += f" - {calendar['name']}"
    venue = " - ".join(b for b in (calendar["exchange"], calendar["currency"]) if b)
    if venue:
        head += f"  ({venue})"
    lines.append(head)

    nxt = calendar["next_earnings"]
    lines.append("\nNext earnings")
    if nxt is None:
        lines.append("  No earnings date from Yahoo")
    else:
        if nxt["date_end"] != nxt["date"]:
            when = f"{nxt['date']} to {nxt['date_end']}"
        else:
            when = nxt["datetime_utc"].replace("T", " ").replace("Z", " UTC")
        kind = "estimated" if nxt["is_estimate"] else "confirmed"
        lines.append(f"  {'Date':<18} {when}  ({kind}, {nxt['status']})")
        cur = calendar["reporting_currency"]
        for label, key, fmt in (("EPS estimate", "eps_estimate", _fmt_money),
                                ("Revenue estimate", "revenue_estimate", _fmt_big)):
            text = _fmt_range(nxt[key], fmt)
            if nxt[key]:
                text += f" {cur}"
            lines.append(f"  {label:<18} {text}".rstrip())

    div = calendar["dividend"]
    lines.append("\nDividend")
    if div is None:
        lines.append("  No dividend dates from Yahoo")
    else:
        for label, key in (("Ex-dividend date", "ex_dividend"), ("Payment date", "payment")):
            date = div[f"{key}_date"]
            text = f"{date}  ({div[f'{key}_status']})" if date else "-"
            lines.append(f"  {label:<18} {text}")
        amount = "-"
        if div["last_amount"] is not None:
            # Sub-unit dividends (0.023625) would round away at 2 places.
            value = div["last_amount"]
            amount = _fmt_money(value) if value >= 1 else f"{value:.4f}".rstrip("0").rstrip(".")
            amount += f" {div['amount_currency']}" if div["amount_currency"] else " (currency not stated by Yahoo)"
            if div["last_amount_date"]:
                amount += f"  (ex-date {div['last_amount_date']})"
        lines.append(f"  {'Last dividend':<18} {amount}")

    history = calendar["earnings_history"]
    lines.append(f"\nEarnings history (EPS, {calendar['reporting_currency']})".replace(", )", ")"))
    if not history:
        lines.append("  No past quarters from Yahoo")
    else:
        lines.append(f"  {'Quarter end':<12} {'Fiscal Q':<9} {'Reported':<11} {'Estimate':>9} {'Actual':>9} {'Surprise':>9}")
        for row in history:
            lines.append(
                f"  {row['quarter_end']:<12} {row['fiscal_quarter'] or '-':<9} "
                f"{row['reported_date'] or '-':<11} {_fmt_money(row['eps_estimate']):>9} "
                f"{_fmt_money(row['eps_actual']):>9} {_fmt_signed_pct(row['surprise_pct']):>9}"
            )

    lines.append(
        "\nNotes: dates and analyst estimates from Yahoo Finance; earnings times are\n"
        "UTC. Yahoo keeps the last dividend dates until new ones are announced, so\n"
        "check the upcoming/past flag. EPS is Yahoo's per-share figure in the\n"
        "reporting currency, which can differ from the trading currency."
    )
    return "\n".join(lines)


def build_json(symbol, calendar):
    return {"symbol": symbol, **calendar}


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Retrieve a stock's earnings calendar and EPS history from Yahoo Finance.",
    )
    parser.add_argument(
        "symbol", help="Ticker in Yahoo notation, e.g. AAPL, VOD.L, D05.SI, SAP.DE"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    try:
        view = stock_data.earnings_view(args.symbol)
    except (requests.RequestException, ValueError, KeyError) as exc:
        die(f"failed to fetch earnings calendar for {args.symbol!r}: {exc}", args.json)

    calendar = extract_calendar(view)
    if calendar["next_earnings"] is None and not calendar["earnings_history"]:
        die(
            f"no earnings data for {args.symbol!r} (only company stocks have earnings)",
            args.json,
        )

    symbol = args.symbol.upper()
    if args.json:
        print(json.dumps(build_json(symbol, calendar), indent=2))
    else:
        print(build_report(symbol, calendar))


if __name__ == "__main__":
    main()
