#!/usr/bin/env python3
"""
Report the top movers on a given stock market right now - the highest-volume
stocks, the biggest gainers, or the biggest losers - through
stock_data.top_movers(), which serves them from Yahoo Finance's public
screeners today. No API key required.

The markets offered (us, nyse, nasdaq, uk, japan, ...) are the ones the
provider covers, from stock_data.mover_markets(). Behind it, Yahoo's keyless
predefined screeners serve the US markets and its generic equity screener
(with a crumb + cookie) the rest, and gainers and losers ignore stocks
trading fewer than 50,000 shares.

Supports --json for structured output so an agent can parse stdout
instead of the human-readable report. On failure the process exits
non-zero and prints {"error": "..."} to stderr.
"""

import argparse
import json

import requests

import stock_data
from cli_utils import die, positive_int, use_utf8_output

DEFAULT_LIMIT = 10
DEFAULT_MARKET = "us"
DEFAULT_METRIC = "volume"

METRIC_LABELS = {
    "volume": "stock(s) by volume",
    "gainers": "gainers",
    "losers": "losers",
}


def quote_to_dict(rank, row):
    """One output record from a stock_data.top_movers() row, with display defaults."""
    return {
        "rank": rank,
        "symbol": "?" if row["symbol"] is None else row["symbol"],
        "name": row["name"] or "(unknown)",
        "exchange": row["exchange"] or "?",
        "volume": row["volume"] or 0,
        "price": row["price"] or 0,
        "change_percent": row["change_percent"] or 0,
        "currency": row["currency"] or "",
    }


def format_quote(row, metric):
    volume = f"Volume: {row['volume']:,}"
    price = f"Price: {row['price']:,.2f} {row['currency']}".rstrip()
    change = f"Change: {row['change_percent']:+.2f}%"
    # Lead with the stat the metric ranks on.
    stats = [change, price, volume] if metric != "volume" else [volume, price, change]
    return "\n".join(
        [
            f"{row['rank']}. {row['symbol']} - {row['name']} ({row['exchange']})",
            "   " + "  |  ".join(stats),
        ]
    )


def parse_args(argv=None):
    markets = sorted(stock_data.mover_markets())
    parser = argparse.ArgumentParser(
        description="Report the top movers (volume, gainers, or losers) on a given market."
    )
    parser.add_argument(
        "--market",
        choices=markets,
        default=DEFAULT_MARKET,
        metavar="MARKET",
        help=(
            "Market to query (default: %(default)s). One of: "
            + ", ".join(markets)
        ),
    )
    parser.add_argument(
        "--metric",
        choices=sorted(stock_data.MOVER_METRICS),
        default=DEFAULT_METRIC,
        help=(
            "Which movers to return (default: %(default)s): "
            "volume = most shares traded, gainers = biggest %% rise, "
            "losers = biggest %% fall."
        ),
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=DEFAULT_LIMIT,
        help="Number of stocks to return (default: %(default)s). Use 1 for the single leader.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    try:
        movers = stock_data.top_movers(args.market, args.metric, args.limit)["movers"]
    except (requests.RequestException, KeyError, ValueError) as exc:
        die(f"failed to fetch {args.metric} for market '{args.market}': {exc}", args.json)

    rows = [quote_to_dict(rank, m) for rank, m in enumerate(movers, start=1)]

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    if not rows:
        print(f"No {args.metric} data returned for market '{args.market}'.")
        return

    label = METRIC_LABELS[args.metric]
    print(f"Top {len(rows)} {label} on {args.market.upper()}:\n")
    for row in rows:
        print(format_quote(row, args.metric))
        print()


if __name__ == "__main__":
    main()
