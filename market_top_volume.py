#!/usr/bin/env python3
"""
Report the top movers on a given stock market right now - the highest-volume
stocks, the biggest gainers, or the biggest losers - using Yahoo Finance's
public screeners. No API key required.

For US markets (us / nyse / nasdaq / amex) this uses the keyless predefined
screeners ("most_actives", "day_gainers", "day_losers") and filters by
listing exchange.

For every other market it fetches a Yahoo crumb + cookie and calls the
generic equity screener, sorted by the chosen metric and filtered to the
market's region (and, where useful, its primary exchange).

Supports --json for structured output so an agent can parse stdout
instead of the human-readable report. On failure the process exits
non-zero and prints {"error": "..."} to stderr.
"""

import argparse
import json

import requests

from cli_utils import die

# Yahoo rejects requests without a browser-like User-Agent.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
REQUEST_TIMEOUT = 15
DEFAULT_LIMIT = 10
DEFAULT_MARKET = "us"
DEFAULT_METRIC = "volume"
# Gainer/loser lists are dominated by illiquid micro-caps unless a floor is
# applied; ignore anything trading fewer shares than this for those metrics.
MIN_MOVER_VOLUME = 50_000

PREDEFINED_URL = (
    "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
)
SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener"
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
COOKIE_URL = "https://fc.yahoo.com"

# metric -> how to ask each screener for it
#   scr_id:     predefined screener id (US markets)
#   sort_field: generic-screener sort field (other markets)
#   sort_type:  generic-screener sort direction
#   reverse:    local sort direction (True = descending)
METRICS = {
    "volume": {
        "scr_id": "most_actives",
        "sort_field": "dayvolume",
        "sort_type": "DESC",
        "key": "regularMarketVolume",
        "reverse": True,
    },
    "gainers": {
        "scr_id": "day_gainers",
        "sort_field": "percentchange",
        "sort_type": "DESC",
        "key": "regularMarketChangePercent",
        "reverse": True,
    },
    "losers": {
        "scr_id": "day_losers",
        "sort_field": "percentchange",
        "sort_type": "ASC",
        "key": "regularMarketChangePercent",
        "reverse": False,
    },
}
METRIC_LABELS = {
    "volume": "stock(s) by volume",
    "gainers": "gainers",
    "losers": "losers",
}

# market alias -> config
#   region:    Yahoo region code (lowercase) used by the generic screener
#   exchanges: set of Yahoo listing-exchange codes to keep, or None for all
#   predefined: True to use the keyless US predefined screeners
MARKETS = {
    # United States
    "us": {"region": "us", "exchanges": None, "predefined": True},
    "nyse": {"region": "us", "exchanges": {"NYQ"}, "predefined": True},
    "nasdaq": {"region": "us", "exchanges": {"NMS", "NCM", "NGM"}, "predefined": True},
    "amex": {"region": "us", "exchanges": {"ASE", "PCX"}, "predefined": True},
    # Rest of world (generic screener)
    "uk": {"region": "gb", "exchanges": {"LSE"}, "predefined": False},
    "lse": {"region": "gb", "exchanges": {"LSE"}, "predefined": False},
    "germany": {"region": "de", "exchanges": {"GER", "FRA"}, "predefined": False},
    "xetra": {"region": "de", "exchanges": {"GER"}, "predefined": False},
    "france": {"region": "fr", "exchanges": {"PAR"}, "predefined": False},
    "euronext-paris": {"region": "fr", "exchanges": {"PAR"}, "predefined": False},
    "netherlands": {"region": "nl", "exchanges": {"AMS"}, "predefined": False},
    "spain": {"region": "es", "exchanges": {"MCE"}, "predefined": False},
    "italy": {"region": "it", "exchanges": {"MIL"}, "predefined": False},
    "switzerland": {"region": "ch", "exchanges": {"EBS", "VTX"}, "predefined": False},
    "sweden": {"region": "se", "exchanges": {"STO"}, "predefined": False},
    "canada": {"region": "ca", "exchanges": {"TOR"}, "predefined": False},
    "tsx": {"region": "ca", "exchanges": {"TOR"}, "predefined": False},
    "australia": {"region": "au", "exchanges": {"ASX"}, "predefined": False},
    "asx": {"region": "au", "exchanges": {"ASX"}, "predefined": False},
    "india": {"region": "in", "exchanges": {"NSI", "BSE"}, "predefined": False},
    "nse": {"region": "in", "exchanges": {"NSI"}, "predefined": False},
    "bse": {"region": "in", "exchanges": {"BSE"}, "predefined": False},
    "hongkong": {"region": "hk", "exchanges": {"HKG"}, "predefined": False},
    "hkex": {"region": "hk", "exchanges": {"HKG"}, "predefined": False},
    "japan": {"region": "jp", "exchanges": {"JPX", "TYO"}, "predefined": False},
    "singapore": {"region": "sg", "exchanges": {"SES"}, "predefined": False},
    "newzealand": {"region": "nz", "exchanges": {"NZE"}, "predefined": False},
    "brazil": {"region": "br", "exchanges": {"SAO"}, "predefined": False},
}


def _session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch_predefined_quotes(session, scr_id):
    params = {
        "formatted": "false",
        "lang": "en-US",
        "region": "US",
        "scrIds": scr_id,
        "count": 250,
    }
    response = session.get(PREDEFINED_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()["finance"]["result"][0]["quotes"]


def fetch_region_quotes(session, region, sort_field, sort_type, min_volume=None):
    # A crumb is required for the generic screener; it is tied to the
    # cookies set by the first request.
    session.get(COOKIE_URL, timeout=REQUEST_TIMEOUT)
    crumb = session.get(CRUMB_URL, timeout=REQUEST_TIMEOUT).text.strip()
    if not crumb or "<html" in crumb.lower():
        raise requests.RequestException("could not obtain a Yahoo Finance crumb")

    operands = [{"operator": "EQ", "operands": ["region", region]}]
    if min_volume:
        operands.append({"operator": "GT", "operands": ["dayvolume", min_volume]})

    body = {
        "size": 100,
        "offset": 0,
        "sortField": sort_field,
        "sortType": sort_type,
        "quoteType": "EQUITY",
        "query": {"operator": "AND", "operands": operands},
        "userId": "",
        "userIdType": "guid",
    }
    response = session.post(
        SCREENER_URL,
        params={"crumb": crumb},
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    error = payload.get("finance", {}).get("error")
    if error:
        raise requests.RequestException(str(error))
    return payload["finance"]["result"][0]["quotes"]


def get_movers(market, metric, limit):
    config = MARKETS[market]
    spec = METRICS[metric]
    session = _session()
    is_mover = metric != "volume"

    if config["predefined"]:
        quotes = fetch_predefined_quotes(session, spec["scr_id"])
    else:
        quotes = fetch_region_quotes(
            session,
            config["region"],
            spec["sort_field"],
            spec["sort_type"],
            min_volume=MIN_MOVER_VOLUME if is_mover else None,
        )

    if config["exchanges"]:
        quotes = [q for q in quotes if q.get("exchange") in config["exchanges"]]

    if is_mover:
        # Drop stale/illiquid quotes that slip past the server-side filter.
        quotes = [
            q for q in quotes
            if (q.get("regularMarketVolume") or 0) >= MIN_MOVER_VOLUME
        ]

    quotes.sort(
        key=lambda q: q.get(spec["key"]) or 0,
        reverse=spec["reverse"],
    )
    return quotes[:limit]


def quote_to_dict(rank, quote):
    return {
        "rank": rank,
        "symbol": quote.get("symbol", "?"),
        "name": quote.get("shortName") or quote.get("longName") or "(unknown)",
        "exchange": quote.get("fullExchangeName") or quote.get("exchange") or "?",
        "volume": quote.get("regularMarketVolume") or 0,
        "price": quote.get("regularMarketPrice") or 0,
        "change_percent": quote.get("regularMarketChangePercent") or 0,
        "currency": quote.get("currency") or "",
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
    parser = argparse.ArgumentParser(
        description="Report the top movers (volume, gainers, or losers) on a given market."
    )
    parser.add_argument(
        "--market",
        choices=sorted(MARKETS),
        default=DEFAULT_MARKET,
        metavar="MARKET",
        help=(
            "Market to query (default: %(default)s). One of: "
            + ", ".join(sorted(MARKETS))
        ),
    )
    parser.add_argument(
        "--metric",
        choices=sorted(METRICS),
        default=DEFAULT_METRIC,
        help=(
            "Which movers to return (default: %(default)s): "
            "volume = most shares traded, gainers = biggest %% rise, "
            "losers = biggest %% fall."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
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
    args = parse_args(argv)
    limit = max(1, args.limit)

    try:
        quotes = get_movers(args.market, args.metric, limit)
    except (requests.RequestException, KeyError, ValueError) as exc:
        die(f"failed to fetch {args.metric} for market '{args.market}': {exc}", args.json)

    rows = [quote_to_dict(rank, q) for rank, q in enumerate(quotes, start=1)]

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
