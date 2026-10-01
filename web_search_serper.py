#!/usr/bin/env python3
"""
Retrieve the top web search results for a query, using the Serper
Google Search API: https://serper.dev/

Requires a SERPER_API_KEY, set as an environment variable or in a .env
file in the current directory. Get one (free tier: 2,500 one-time
credits) by registering at https://serper.dev/

Real environment variables always take precedence over .env values.

(See web_search_brave.py's docstring for why Google's own Programmable
Search Engine and scraping DuckDuckGo's HTML were ruled out for those
scripts. Serper is a fourth option, alongside SerpApi: it also proxies
Google's actual search results through an official, supported API, at
the cost of a paid-tier-optional subscription and a dependency on a
third-party scraping service rather than a first-party search index
like Brave's.)

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse

import requests

from cli_utils import die, load_dotenv, positive_int, print_results, require_env

SEARCH_URL = "https://google.serper.dev/search"
REQUEST_TIMEOUT = 10

RESULTS_TO_SHOW = 10
# Serper's Google engine caps organic results at 100 per page.
MAX_RESULTS_PER_REQUEST = 100


def fetch_results(query, limit, api_key):
    results = []
    page = 1
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    while len(results) < limit:
        page_size = min(MAX_RESULTS_PER_REQUEST, limit - len(results))
        payload = {
            "q": query,
            "num": page_size,
            "page": page,
        }
        response = requests.post(
            SEARCH_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()

        # Serper reports failures (e.g. an invalid key) as a 200 response
        # with a "message" field rather than a non-2xx status.
        if "message" in data and "organic" not in data:
            raise requests.RequestException(data["message"])

        items = data.get("organic", [])
        results.extend(items)
        if len(items) < page_size:
            break
        page += 1

    return results[:limit]


def result_to_dict(rank, item):
    """Flatten a raw API result into the record used for both output modes."""
    return {
        "rank": rank,
        "title": item.get("title", "(no title)"),
        "url": item.get("link", ""),
        "snippet": item.get("snippet", "").replace("\n", " "),
    }


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

    load_dotenv()
    api_key = require_env("SERPER_API_KEY", "web_search_serper.py", args.json)

    if not args.json:
        print(f"Searching for: {args.query}\n")

    try:
        items = fetch_results(args.query, args.limit, api_key)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    rows = [result_to_dict(rank, item) for rank, item in enumerate(items, start=1)]
    print_results(rows, args.json)


if __name__ == "__main__":
    main()
