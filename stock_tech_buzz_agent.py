#!/usr/bin/env python3
"""
Agent that cross-references the top highest-volume NYSE and Nasdaq stocks
with the hottest technology discussions on Hacker News, and reports which
stocks (if any) are being talked about.

Combines market_top_volume.py (top 10 by volume on each of NYSE and
Nasdaq) and hottest_tech_discussions.py (top 50 tech discussions), then
matches each stock's ticker symbol and company name against each
discussion's title.

No API key required. Supports a --json flag for structured output, so
this script can be called as a tool by an agent: it parses stdout
instead of a human-readable report.
"""

import argparse
import json
import re
import sys

import requests

import hottest_tech_discussions as hn
import market_top_volume as market

STOCK_LIMIT_PER_EXCHANGE = 10
DISCUSSION_LIMIT = 50
EXCHANGES = ("nyse", "nasdaq")

# Legal-entity suffixes stripped from company names before matching, so
# "NVIDIA Corporation" becomes "NVIDIA" and "Nu Holdings Ltd." becomes
# "Nu Holdings". Only one suffix is stripped (the outermost) so distinctive
# multi-word names like "Nu Holdings" are preserved rather than reduced to
# a single generic word.
NAME_SUFFIXES = re.compile(
    r",?\s+(incorporated|corporation|corp\.?|inc\.?|limited|ltd\.?|"
    r"holdings?|group|company|co\.?|plc|s\.a\.?|n\.v\.?|ag|se|l\.p\.?|lp|llc)$",
    re.IGNORECASE,
)

# Ticker symbols that double as common English words/acronyms. Matching
# these case-sensitively as whole words in a headline is too noisy to be
# a reliable signal, so they're excluded from symbol matching (company
# name matching still applies).
AMBIGUOUS_SYMBOLS = {
    "A", "AI", "ALL", "AN", "ARE", "AS", "AT", "BE", "BY", "CAT", "DO",
    "FOR", "GO", "I", "IN", "IS", "IT", "ME", "MY", "NOW", "OF", "ON",
    "OR", "SO", "THE", "TO", "UP", "US", "WE",
}


def normalize_company_name(name):
    return NAME_SUFFIXES.sub("", name.strip()).strip()


def stock_mentions_in_title(quote, title):
    symbol = quote.get("symbol", "")
    if symbol and symbol not in AMBIGUOUS_SYMBOLS:
        if re.search(rf"\b{re.escape(symbol)}\b", title):
            return True

    raw_name = quote.get("shortName") or quote.get("longName") or ""
    name = normalize_company_name(raw_name)
    if len(name) >= 3:
        if re.search(rf"\b{re.escape(name)}\b", title, re.IGNORECASE):
            return True

    return False


def get_top_volume_stocks(limit_per_exchange=STOCK_LIMIT_PER_EXCHANGE):
    stocks = []
    seen_symbols = set()
    for exchange in EXCHANGES:
        for quote in market.get_movers(exchange, "volume", limit_per_exchange):
            if quote.get("symbol") in seen_symbols:
                continue
            seen_symbols.add(quote.get("symbol"))
            stocks.append({**quote, "_exchange": exchange})
    return stocks


def find_stock_buzz(limit_per_exchange=STOCK_LIMIT_PER_EXCHANGE, discussion_limit=DISCUSSION_LIMIT):
    stocks = get_top_volume_stocks(limit_per_exchange)
    discussions = hn.get_hottest_tech_discussions(limit=discussion_limit)

    results = []
    for stock in stocks:
        matches = [d for d in discussions if stock_mentions_in_title(stock, d.get("title", ""))]
        if matches:
            results.append({"stock": stock, "discussions": matches})

    return results, stocks, discussions


def result_to_dict(result):
    stock = result["stock"]
    return {
        "symbol": stock.get("symbol", "?"),
        "name": stock.get("shortName") or stock.get("longName") or "(unknown)",
        "exchange": stock["_exchange"].upper(),
        "volume": stock.get("regularMarketVolume", 0),
        "price": stock.get("regularMarketPrice", 0),
        "change_percent": stock.get("regularMarketChangePercent", 0),
        "discussions": [
            {
                "title": d.get("title", "(no title)"),
                "score": d.get("score", 0),
                "comments": d.get("descendants", 0),
                "discussion_url": f"https://news.ycombinator.com/item?id={d['id']}",
            }
            for d in result["discussions"]
        ],
    }


def format_result(rank, result):
    stock = result["stock"]
    symbol = stock.get("symbol", "?")
    name = stock.get("shortName") or stock.get("longName") or "(unknown)"
    exchange = stock["_exchange"].upper()
    volume = stock.get("regularMarketVolume", 0)

    lines = [f"{rank}. {symbol} - {name} ({exchange}, Volume: {volume:,})"]
    for d in result["discussions"]:
        title = d.get("title", "(no title)")
        score = d.get("score", 0)
        discussion_url = f"https://news.ycombinator.com/item?id={d['id']}"
        lines.append(f"   - \"{title}\" (Score: {score})")
        lines.append(f"     {discussion_url}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Find top-volume NYSE/Nasdaq stocks that are mentioned in the "
            "hottest current tech discussions on Hacker News."
        )
    )
    parser.add_argument(
        "--stock-limit",
        type=int,
        default=STOCK_LIMIT_PER_EXCHANGE,
        help=f"Number of top-volume stocks to pull per exchange (default: {STOCK_LIMIT_PER_EXCHANGE})",
    )
    parser.add_argument(
        "--discussion-limit",
        type=int,
        default=DISCUSSION_LIMIT,
        help=f"Number of hottest tech discussions to search (default: {DISCUSSION_LIMIT})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if not args.json:
        print(
            f"Fetching top {args.stock_limit} NYSE + top {args.stock_limit} Nasdaq stocks by "
            f"volume, and searching the top {args.discussion_limit} tech discussions...\n"
        )

    try:
        results, stocks, discussions = find_stock_buzz(
            limit_per_exchange=args.stock_limit, discussion_limit=args.discussion_limit
        )
    except requests.RequestException as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
        else:
            print(f"Error fetching data: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps([result_to_dict(r) for r in results], indent=2))
        return

    if not results:
        print(
            f"No overlap found between the top {len(stocks)} volume stocks and the "
            f"top {len(discussions)} tech discussions."
        )
        return

    for rank, result in enumerate(results, start=1):
        print(format_result(rank, result))
        print()


if __name__ == "__main__":
    main()
