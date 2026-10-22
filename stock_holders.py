#!/usr/bin/env python3
"""
Retrieve who owns a stock and what its insiders have been doing, through
stock_data.holders_view(), which serves it from Yahoo Finance's public
``quoteSummary`` endpoint today. No API key or authentication required
(yahoo_finance.py fetches a cookie + crumb automatically).

Give it a ticker in Yahoo's notation (AAPL, VOD.L, D05.SI, SAP.DE, ...). The
script reports:

- ownership           the share held by insiders and by institutions, and
                      how many institutions hold it
- insider activity    each insider transaction in the last --days days
                      (default 180), newest first, sorted into kinds (sale,
                      purchase, option exercise, award, gift, company
                      buyback, holder disclosure, other, unspecified), with
                      totals for sales and purchases kept apart from the rest
- top holders         the top funds, and for US listings the top
                      institutions, each with its report date

Yahoo's 6-month "net share purchase" summary is not used: it counts stock
awards as buys. For non-US listings the transaction list is mostly company
buybacks and large-holder disclosures, and the institution list holds only
small US filers, so that list is left out. Supports --json for structured
output. On failure the process exits non-zero and prints {"error": "..."}
to stderr.
"""

import argparse
import json

import requests

import stock_data
from cli_utils import die, positive_int, use_utf8_output
from stock_intrinsic_value import _fmt_money

DEFAULT_DAYS = 180

KIND_LABELS = {
    "sale": "sale", "purchase": "purchase", "option_exercise": "exercise",
    "award": "award", "gift": "gift", "buyback": "buyback",
    "holder_disclosure": "holder", "other": "other", "unspecified": "?",
}
# Kinds that are an insider's own buying or selling decision.
TRADE_KINDS = ("sale", "purchase")
# What --trades-only keeps in the transaction list (exercises turn options
# into shares, so they are kept alongside the trades).
TRADES_ONLY_KINDS = ("sale", "purchase", "option_exercise")
BY_INSIDER_TO_SHOW = 10


# --------------------------------------------------------------------------- #
# Shape                                                                        #
# --------------------------------------------------------------------------- #
def _totals(rows):
    return {
        "count": len(rows),
        "shares": sum(t["shares"] or 0 for t in rows),
        "value": sum(t["value"] or 0 for t in rows),
    }


def insider_summary(transactions):
    """Sales and purchases totalled, overall and per insider; every other
    kind only counted.

    ``by_insider`` lists each insider with at least one sale or purchase,
    most value traded first (then most shares).
    """
    others = {}
    for t in transactions:
        if t["kind"] not in TRADE_KINDS:
            others[t["kind"]] = others.get(t["kind"], 0) + 1

    people = {}
    for t in transactions:
        if t["kind"] in TRADE_KINDS and t["name"]:
            person = people.setdefault(t["name"], {"name": t["name"], "relation": None, "rows": []})
            person["relation"] = person["relation"] or t["relation"]
            person["rows"].append(t)
    by_insider = []
    for person in people.values():
        sales = _totals([t for t in person["rows"] if t["kind"] == "sale"])
        purchases = _totals([t for t in person["rows"] if t["kind"] == "purchase"])
        by_insider.append({"name": person["name"], "relation": person["relation"],
                           "sales": sales, "purchases": purchases})
    by_insider.sort(key=lambda p: (p["sales"]["value"] + p["purchases"]["value"],
                                   p["sales"]["shares"] + p["purchases"]["shares"]), reverse=True)

    return {
        "sales": _totals([t for t in transactions if t["kind"] == "sale"]),
        "purchases": _totals([t for t in transactions if t["kind"] == "purchase"]),
        "other_counts": others,
        "by_insider": by_insider,
    }


def extract_holders(view, days=DEFAULT_DAYS, trades_only=False):
    """Turn stock_data.holders_view()'s ``view`` into the JSON-shaped dict
    (without ``symbol``).

    With ``trades_only`` the transaction list keeps only TRADES_ONLY_KINDS;
    the summary is still worked out from every transaction.
    """
    transactions = view["transactions"]
    return {
        "name": view["name"],
        "exchange": view["exchange"],
        "currency": view["currency"],
        "us_listing": view["us_listing"],
        "transaction_currency": view["transaction_currency"],
        "ownership": view["ownership"],
        "days": days,
        "trades_only": trades_only,
        "insider_summary": insider_summary(transactions),
        "transactions": [t for t in transactions if t["kind"] in TRADES_ONLY_KINDS]
        if trades_only else transactions,
        "top_funds": view["top_funds"],
        "top_institutions": view["top_institutions"],
    }


def transaction_count(data):
    """All transactions in the window, including any --trades-only left out."""
    s = data["insider_summary"]
    return s["sales"]["count"] + s["purchases"]["count"] + sum(s["other_counts"].values())


def has_data(data):
    return (
        any(v is not None for v in data["ownership"].values())
        or transaction_count(data) > 0
        or bool(data["top_funds"])
        or bool(data["top_institutions"])
    )


# --------------------------------------------------------------------------- #
# Output                                                                       #
# --------------------------------------------------------------------------- #
def _pct(value):
    return "-" if value is None else f"{value * 100:.2f}%"


def _signed_pct(value):
    return "-" if value is None else f"{value * 100:+.2f}%"


def _count(value):
    return "-" if value is None else f"{value:,}"


def _price(row):
    if row["price_low"] is None:
        return "-"
    if row["price_high"] != row["price_low"]:
        return f"{_fmt_money(row['price_low'])}-{_fmt_money(row['price_high'])}"
    return _fmt_money(row["price_low"])


def _holder_lines(title, rows):
    lines = [f"\n{title}"]
    if not rows:
        lines.append("  None reported by Yahoo")
        return lines
    lines.append(f"  {'Holder':<46} {'Held':>7} {'Change':>8} {'Shares':>15}  As of")
    for row in rows:
        lines.append(
            f"  {(row['name'] or '?')[:46]:<46} {_pct(row['pct_held']):>7} "
            f"{_signed_pct(row['pct_change']):>8} {_count(row['shares']):>15}  {row['report_date'] or '-'}"
        )
    return lines


def build_report(symbol, data):
    lines = []
    head = symbol
    if data["name"]:
        head += f" - {data['name']}"
    venue = " - ".join(b for b in (data["exchange"], data["currency"]) if b)
    if venue:
        head += f"  ({venue})"
    lines.append(head)

    own = data["ownership"]
    lines.append(
        f"\nOwnership  insiders {_pct(own['insiders_pct'])}    institutions "
        f"{_pct(own['institutions_pct'])} ({_pct(own['institutions_float_pct'])} of float)    "
        f"{_count(own['institutions_count'])} institutions"
    )

    days = data["days"]
    lines.append(f"\nInsider activity (last {days} days)")
    if not transaction_count(data):
        lines.append(f"  No insider transactions from Yahoo in the last {days} days")
    else:
        s = data["insider_summary"]
        for label, key in (("Sales", "sales"), ("Purchases", "purchases")):
            t = s[key]
            lines.append(
                f"  {label:<10} {t['count']:>4}  {_count(t['shares']):>15} shares"
                f"  {_fmt_money(t['value']) if t['value'] else '-':>16} value"
            )
        if s["other_counts"]:
            others = ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(s["other_counts"].items()))
            lines.append(f"  Other      {others}")

        if s["by_insider"]:
            lines.append(f"\n  {'By insider':<26} {'Role':<22} {'Sold':>13} {'Sale value':>16} "
                         f"{'Bought':>11} {'Buy value':>14}")
            for p in s["by_insider"][:BY_INSIDER_TO_SHOW]:
                lines.append(
                    f"  {(p['name'] or '?')[:26]:<26} {(p['relation'] or '-')[:22]:<22} "
                    f"{_count(p['sales']['shares']):>13} "
                    f"{_fmt_money(p['sales']['value']) if p['sales']['value'] else '-':>16} "
                    f"{_count(p['purchases']['shares']):>11} "
                    f"{_fmt_money(p['purchases']['value']) if p['purchases']['value'] else '-':>14}"
                )
            if len(s["by_insider"]) > BY_INSIDER_TO_SHOW:
                lines.append(f"  ... and {len(s['by_insider']) - BY_INSIDER_TO_SHOW} more")

        if data["trades_only"]:
            lines.append("\n  Showing sales, purchases and option exercises only (--trades-only)")
        if not data["transactions"]:
            lines.append("  No sales, purchases or option exercises in the window")
        else:
            lines.append(f"\n  {'Date':<11} {'Name':<24} {'Role':<22} {'Kind':<9} {'Shares':>13} "
                         f"{'Price':>15} {'Value':>16}")
        for t in data["transactions"]:
            lines.append(
                f"  {t['date']:<11} {(t['name'] or '?')[:24]:<24} {(t['relation'] or '-')[:22]:<22} "
                f"{KIND_LABELS[t['kind']]:<9} {_count(t['shares']):>13} {_price(t):>15} "
                f"{_fmt_money(t['value']) if t['value'] else '-':>16}"
            )

    lines += _holder_lines("Top funds", data["top_funds"])
    if data["us_listing"]:
        lines += _holder_lines("Top institutions", data["top_institutions"])
    else:
        lines.append("\nTop institutions  not shown for non-US listings "
                     "(Yahoo lists only small US filers)")

    notes = [
        "\nNotes: ownership as aggregated by Yahoo Finance; holder lists are",
        "periodic filings (see the As-of dates), not live, though a holder's",
        "value is its reported shares at today's price, in the quote currency.",
        "Awards, gifts, exercises and buybacks are counted apart from sales",
        "and purchases.",
    ]
    if not data["us_listing"]:
        notes.append("For non-US listings many transactions are company buybacks or")
        notes.append("large-holder disclosures (including directors' holding notices).")
        notes.append(f"Insider-trade prices and values appear to be in USD, not "
                     f"{data['currency'] or 'the quote currency'}: Yahoo doesn't")
        notes.append("label them, but they match the local price converted to dollars.")
    lines += notes
    return "\n".join(lines)


def build_json(symbol, data):
    return {"symbol": symbol, **data}


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Retrieve a stock's ownership, insider transactions and top "
                    "holders from Yahoo Finance.",
    )
    parser.add_argument(
        "symbol", help="Ticker in Yahoo notation, e.g. AAPL, VOD.L, D05.SI, SAP.DE"
    )
    parser.add_argument(
        "--days", type=positive_int, default=DEFAULT_DAYS,
        help=f"Days of insider transactions to list (default {DEFAULT_DAYS}).",
    )
    parser.add_argument(
        "--trades-only", action="store_true",
        help="List only sales, purchases and option exercises (the summary still "
             "counts every transaction).",
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
        view = stock_data.holders_view(args.symbol, args.days)
    except (requests.RequestException, ValueError, KeyError) as exc:
        die(f"failed to fetch holders for {args.symbol!r}: {exc}", args.json)

    symbol = args.symbol.upper()
    data = extract_holders(view, args.days, trades_only=args.trades_only)
    if not has_data(data):
        die(
            f"no ownership data for {args.symbol!r} (only company stocks have holders)",
            args.json,
        )

    if args.json:
        print(json.dumps(build_json(symbol, data), indent=2))
    else:
        print(build_report(symbol, data))


if __name__ == "__main__":
    main()
