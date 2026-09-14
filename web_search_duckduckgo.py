#!/usr/bin/env python3
"""
Retrieve the top web search results for a query, by scraping DuckDuckGo's
HTML search results via the `ddgs` package: https://pypi.org/project/ddgs/

No API key required. This is an unofficial method - DuckDuckGo has no
supported search API - so it can get rate-limited under sustained use,
even from residential IPs (see web_search_brave.py, which uses Brave's
official API for that reason). Use this script when an occasional,
key-free lookup is enough; prefer web_search_brave.py for anything
higher-volume or production-facing.

Use `ddgs`, not its predecessor `duckduckgo_search` (renamed in 2025).
`duckduckgo_search` is unmaintained and hits DuckDuckGo's rate limit
almost immediately; `ddgs` is the actively maintained successor and is
far less rate-limit-prone. `ddgs` requires Python >=3.10 - the fallback
import of `duckduckgo_search` below exists only for older interpreters
that can't install `ddgs`, and should be treated as a degraded mode
(expect frequent "202 Ratelimit" errors), not an equivalent substitute.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json

try:
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException
except ImportError:
    # Degraded fallback for Python <3.10, where ddgs can't be installed.
    # This unmaintained predecessor package rate-limits much more readily.
    try:
        from duckduckgo_search import DDGS
        from duckduckgo_search.exceptions import (
            DuckDuckGoSearchException as DDGSException,
        )
    except ImportError:
        DDGS = None
        DDGSException = Exception

from cli_utils import die, positive_int

RESULTS_TO_SHOW = 10


def fetch_results(query, limit):
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=limit))


def result_to_dict(rank, item):
    """Flatten a raw ddgs result into the record used for both output modes."""
    return {
        "rank": rank,
        "title": item.get("title", "(no title)"),
        "url": item.get("href", ""),
        "snippet": item.get("body", "").replace("\n", " "),
    }


def format_result(row):
    """Render a result record from result_to_dict() as a text block."""
    lines = [
        f"{row['rank']}. {row['title']}",
        f"   {row['url']}",
        f"   {row['snippet']}",
    ]
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Retrieve the top web search results for a query."
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=RESULTS_TO_SHOW,
        help=f"Number of results to return (default: {RESULTS_TO_SHOW})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if DDGS is None:
        die(
            "The 'ddgs' package is required. Install it with: pip install ddgs",
            args.json,
        )

    if not args.json:
        print(f"Searching for: {args.query}\n")

    try:
        items = fetch_results(args.query, args.limit)
    except DDGSException as exc:
        die(str(exc), args.json)

    rows = [result_to_dict(rank, item) for rank, item in enumerate(items, start=1)]

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    if not rows:
        print("No results found.")
        return

    for row in rows:
        print(format_result(row))
        print()


if __name__ == "__main__":
    main()
