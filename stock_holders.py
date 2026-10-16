#!/usr/bin/env python3
"""
Retrieve who owns a stock and what its insiders have been doing, from Yahoo
Finance's public ``quoteSummary`` endpoint. No API key or authentication
required (a cookie + crumb are fetched automatically, via
yahoo_finance.fetch_quote_summary()).

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
import re
from datetime import datetime, timezone

import requests

import yahoo_finance as yf
from cli_utils import die, positive_int, use_utf8_output
from stock_intrinsic_value import _fmt_money

MODULES = ["price", "majorHoldersBreakdown", "insiderTransactions",
           "fundOwnership", "institutionOwnership"]
DEFAULT_DAYS = 180

# Transaction descriptions, matched case-insensitively at the start of
# Yahoo's "transactionText" ("Sale at price 222.19 - 223.75 per share.").
KINDS = [
    (r"sale\b|sold\b", "sale"),
    (r"purchase\b|bought\b", "purchase"),
    (r"buy ?back\b", "buyback"),
    (r"conversion of exercise|option exercise", "option_exercise"),
    (r"stock award|grant\b", "award"),
    (r"stock gift|gift\b", "gift"),
]
KIND_LABELS = {
    "sale": "sale", "purchase": "purchase", "option_exercise": "exercise",
    "award": "award", "gift": "gift", "buyback": "buyback",
    "holder_disclosure": "holder", "other": "other", "unspecified": "?",
}
OWNERSHIP = {"D": "direct", "I": "indirect", "D/I": "direct and indirect"}
# Kinds that are an insider's own buying or selling decision.
TRADE_KINDS = ("sale", "purchase")
# What --trades-only keeps in the transaction list (exercises turn options
# into shares, so they are kept alongside the trades).
TRADES_ONLY_KINDS = ("sale", "purchase", "option_exercise")
BY_INSIDER_TO_SHOW = 10
PRICE_RE = re.compile(r"at price ([\d.,]+)(?:\s*-\s*([\d.,]+))?", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Parse                                                                        #
# --------------------------------------------------------------------------- #
def is_us_listing(symbol):
    """Yahoo writes non-US listings with an exchange suffix (VOD.L, 7203.T)."""
    return "." not in symbol


def _name_key(name):
    """The first two words of a company name, lower-cased, for matching."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split()[:2])


def classify(text, filer, relation, company_names):
    """The kind of one insider transaction (see KIND_LABELS)."""
    text = (text or "").strip()
    for pattern, kind in KINDS:
        if re.match(pattern, text, re.IGNORECASE):
            return kind
    if text:
        return "other"
    # No description: the company itself, a large holder, or unknown.
    filer_key = _name_key(filer)
    if filer_key and any(filer_key == _name_key(n) for n in company_names if n):
        return "buyback"
    if not relation:
        return "holder_disclosure"
    return "unspecified"


def _price_range(text):
    """(low, high) per-share price from a description, None for 0 or none."""
    match = PRICE_RE.search(text or "")
    if not match:
        return None, None
    low = float(match.group(1).replace(",", ""))
    high = float(match.group(2).replace(",", "")) if match.group(2) else low
    return (low, high) if low > 0 else (None, None)


def _positive(value):
    return value if value is not None and value > 0 else None


def insider_transactions(modules, company_names, days=DEFAULT_DAYS, now=None):
    """Insider transactions in the last ``days``, newest first.

    ``now`` (epoch seconds) is for tests.
    """
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    cutoff = now - days * 86400
    dated = []
    for entry in (modules.get("insiderTransactions") or {}).get("transactions") or []:
        epoch = yf.summary_num(entry, "startDate")
        if epoch is None or epoch < cutoff:
            continue
        text = yf.summary_text(entry, "transactionText")
        relation = yf.summary_text(entry, "filerRelation")
        filer = yf.summary_text(entry, "filerName")
        low, high = _price_range(text)
        shares = _positive(yf.summary_num(entry, "shares"))
        dated.append((epoch, {
            "date": datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d"),
            "name": filer,
            "relation": relation,
            "kind": classify(text, filer, relation, company_names),
            "text": text,
            "shares": None if shares is None else int(shares),
            "value": _positive(yf.summary_num(entry, "value")),
            "price_low": low,
            "price_high": high,
            "ownership": OWNERSHIP.get(yf.summary_text(entry, "ownership")),
        }))
    dated.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in dated]


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


def holders(modules, module):
    """Top holders from ``fundOwnership`` / ``institutionOwnership``."""
    rows = []
    for entry in (modules.get(module) or {}).get("ownershipList") or []:
        report = yf.summary_num(entry, "reportDate")
        shares = yf.summary_num(entry, "position")
        rows.append({
            "name": yf.summary_text(entry, "organization"),
            "pct_held": yf.summary_num(entry, "pctHeld"),
            "shares": None if shares is None else int(shares),
            "value": yf.summary_num(entry, "value"),
            "pct_change": yf.summary_num(entry, "pctChange"),
            "report_date": None if report is None
            else datetime.fromtimestamp(report, timezone.utc).strftime("%Y-%m-%d"),
        })
    return rows


def extract_holders(symbol, modules, days=DEFAULT_DAYS, now=None, trades_only=False):
    """Flatten the raw modules into the JSON-shaped dict (without ``symbol``).

    With ``trades_only`` the transaction list keeps only TRADES_ONLY_KINDS;
    the summary is still worked out from every transaction.
    """
    def breakdown(key):
        return yf.summary_num(modules, "majorHoldersBreakdown", key)

    long_name = yf.summary_text(modules, "price", "longName")
    short_name = yf.summary_text(modules, "price", "shortName")
    us = is_us_listing(symbol)
    transactions = insider_transactions(modules, [long_name, short_name], days, now)
    count = breakdown("institutionsCount")
    return {
        "name": long_name or short_name,
        "exchange": yf.summary_text(modules, "price", "exchangeName"),
        "currency": yf.summary_text(modules, "price", "currency") or "",
        "us_listing": us,
        # Yahoo doesn't label it. For non-US listings, insider-trade prices
        # matched the local quote converted to US dollars (VOD.L, D05.SI).
        "transaction_currency": (yf.summary_text(modules, "price", "currency") or None) if us else "USD",
        "ownership": {
            "insiders_pct": breakdown("insidersPercentHeld"),
            "institutions_pct": breakdown("institutionsPercentHeld"),
            "institutions_float_pct": breakdown("institutionsFloatPercentHeld"),
            "institutions_count": None if count is None else int(count),
        },
        "days": days,
        "trades_only": trades_only,
        "insider_summary": insider_summary(transactions),
        "transactions": [t for t in transactions if t["kind"] in TRADES_ONLY_KINDS]
        if trades_only else transactions,
        "top_funds": holders(modules, "fundOwnership"),
        "top_institutions": holders(modules, "institutionOwnership") if us else None,
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
        modules = yf.fetch_quote_summary(args.symbol, MODULES)
    except (requests.RequestException, ValueError, KeyError) as exc:
        die(f"failed to fetch holders for {args.symbol!r}: {exc}", args.json)

    symbol = args.symbol.upper()
    data = extract_holders(symbol, modules, args.days, trades_only=args.trades_only)
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
