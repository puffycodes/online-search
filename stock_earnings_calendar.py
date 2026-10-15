#!/usr/bin/env python3
"""
Retrieve a stock's earnings calendar from Yahoo Finance's public
``quoteSummary`` endpoint. No API key or authentication required (a cookie +
crumb are fetched automatically, via yahoo_finance.fetch_quote_summary()).

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

import yahoo_finance as yf
from cli_utils import die
from stock_intrinsic_value import _fmt_big, _fmt_money

MODULES = [
    "price",
    "financialData",
    "defaultKeyStatistics",
    "calendarEvents",
    "earningsHistory",
    "earnings",
]
# Quote currencies in a minor unit (pence, agorot, cents).
MINOR_UNIT_CURRENCIES = {"GBp", "GBX", "ILA", "ZAc"}


# --------------------------------------------------------------------------- #
# Parse                                                                        #
# --------------------------------------------------------------------------- #
def _utc(timestamp):
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)


def _date(timestamp):
    return None if timestamp is None else _utc(timestamp).strftime("%Y-%m-%d")


def _status(date_str, today):
    if date_str is None:
        return None
    return "upcoming" if date_str >= today.isoformat() else "past"


def _estimate(earnings, prefix):
    values = {
        "low": yf.summary_num(earnings, f"{prefix}Low"),
        "average": yf.summary_num(earnings, f"{prefix}Average"),
        "high": yf.summary_num(earnings, f"{prefix}High"),
    }
    return values if any(v is not None for v in values.values()) else None


def next_earnings(modules, today):
    """The next (or latest-known) earnings event from ``calendarEvents``, or None.

    When Yahoo has no confirmed date it gives a window of two timestamps;
    ``date`` is the start and ``date_end`` the end of that window.
    """
    earnings = (modules.get("calendarEvents") or {}).get("earnings") or {}
    stamps = sorted(
        yf.summary_num({"t": t}, "t") for t in earnings.get("earningsDate") or []
    )
    stamps = [int(t) for t in stamps if t is not None]
    if not stamps:
        return None
    date = _date(stamps[0])
    return {
        "date": date,
        "date_end": _date(stamps[-1]),
        "datetime_utc": _utc(stamps[0]).strftime("%Y-%m-%dT%H:%MZ"),
        "is_estimate": bool(earnings.get("isEarningsDateEstimate")) or len(stamps) > 1,
        "status": _status(date, today),
        "eps_estimate": _estimate(earnings, "earnings"),
        "revenue_estimate": _estimate(earnings, "revenue"),
    }


def dividend_dates(modules, today, currency):
    """Ex-dividend / payment dates and the last dividend paid, or None if Yahoo has none.

    ``amount_currency`` is None for minor-unit listings (LSE ``GBp``, ...):
    Yahoo returns their dividend in pounds or the declared currency, not the
    quote's minor unit, and does not say which.
    """
    calendar = modules.get("calendarEvents") or {}
    ex_date = _date(yf.summary_num(calendar, "exDividendDate"))
    pay_date = _date(yf.summary_num(calendar, "dividendDate"))
    last_amount = yf.summary_num(modules, "defaultKeyStatistics", "lastDividendValue")
    if ex_date is None and pay_date is None and last_amount is None:
        return None
    return {
        "ex_dividend_date": ex_date,
        "ex_dividend_status": _status(ex_date, today),
        "payment_date": pay_date,
        "payment_status": _status(pay_date, today),
        "last_amount": last_amount,
        "last_amount_date": _date(
            yf.summary_num(modules, "defaultKeyStatistics", "lastDividendDate")
        ),
        "amount_currency": None if currency in MINOR_UNIT_CURRENCIES else currency or None,
    }


def earnings_history(modules):
    """The last quarters' EPS from ``earningsHistory``, oldest first.

    The report date and fiscal-quarter label come from the ``earnings``
    module's chart, matched on the quarter-end date.
    """
    chart = ((modules.get("earnings") or {}).get("earningsChart") or {}).get("quarterly") or []
    by_end = {}
    for entry in chart:
        end = yf.summary_num(entry, "periodEndDate")
        if end is not None:
            by_end[_date(end)] = entry

    rows = []
    for entry in (modules.get("earningsHistory") or {}).get("history") or []:
        quarter_end = _date(yf.summary_num(entry, "quarter"))
        actual = yf.summary_num(entry, "epsActual")
        estimate = yf.summary_num(entry, "epsEstimate")
        if quarter_end is None or (actual is None and estimate is None):
            continue
        match = by_end.get(quarter_end, {})
        rows.append({
            "quarter_end": quarter_end,
            "fiscal_quarter": yf.summary_text(match, "fiscalQuarter"),
            "reported_date": _date(yf.summary_num(match, "reportedDate")),
            "eps_estimate": estimate,
            "eps_actual": actual,
            "surprise_pct": yf.summary_num(entry, "surprisePercent"),
            "currency": yf.summary_text(entry, "currency"),
        })
    rows.sort(key=lambda r: r["quarter_end"])
    return rows


def extract_calendar(modules, today=None):
    """Flatten the raw modules into the JSON-shaped calendar dict."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    history = earnings_history(modules)
    # EPS and revenue estimates are in the reporting currency, which can differ
    # from the trading currency (VOD.L trades in GBp but reports in EUR).
    reporting = (
        yf.summary_text(modules, "financialData", "financialCurrency")
        or next((r["currency"] for r in reversed(history) if r["currency"]), None)
    )
    currency = yf.summary_text(modules, "price", "currency") or ""
    return {
        "name": yf.summary_text(modules, "price", "longName")
        or yf.summary_text(modules, "price", "shortName"),
        "exchange": yf.summary_text(modules, "price", "exchangeName"),
        "currency": currency,
        "reporting_currency": reporting or currency,
        "next_earnings": next_earnings(modules, today),
        "dividend": dividend_dates(modules, today, currency),
        "earnings_history": history,
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
    args = parse_args(argv)

    try:
        modules = yf.fetch_quote_summary(args.symbol, MODULES)
    except (requests.RequestException, ValueError, KeyError) as exc:
        die(f"failed to fetch earnings calendar for {args.symbol!r}: {exc}", args.json)

    calendar = extract_calendar(modules)
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
