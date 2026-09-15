#!/usr/bin/env python3
"""
Retrieve the top web search results for a query, using the Brave
Search API: https://api-dashboard.search.brave.com/app/documentation/web-search/get-started

Requires a BRAVE_API_KEY, set as an environment variable or in a .env
file in the current directory. Get one (free tier: 2,000 queries/month)
by registering at https://api-dashboard.search.brave.com/register

Real environment variables always take precedence over .env values.

(Google's Programmable Search Engine no longer supports free whole-web
search, and DuckDuckGo has no official search API - scraping its HTML
pages via the duckduckgo_search package gets rate-limited quickly, even
from residential IPs. Brave's API is an official, supported endpoint.)

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import html
import os
import re

import requests

from cli_utils import die, load_dotenv, positive_int, print_results

_TAG_RE = re.compile(r"<[^>]+>")


def strip_markup(text):
    """Strip Brave's <strong> highlighting tags and unescape HTML entities."""
    return html.unescape(_TAG_RE.sub("", text))

SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
REQUEST_TIMEOUT = 10

RESULTS_TO_SHOW = 10
# The API returns at most 20 results per request.
MAX_RESULTS_PER_REQUEST = 20


def fetch_results(query, limit, api_key):
    results = []
    offset = 0
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    while len(results) < limit:
        page_size = min(MAX_RESULTS_PER_REQUEST, limit - len(results))
        params = {
            "q": query,
            "count": page_size,
            "offset": offset,
        }
        response = requests.get(
            SEARCH_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()

        items = payload.get("web", {}).get("results", [])
        results.extend(items)
        if len(items) < page_size:
            break
        offset += 1

    return results[:limit]


def result_to_dict(rank, item):
    """Flatten a raw API result into the record used for both output modes."""
    return {
        "rank": rank,
        "title": strip_markup(item.get("title", "(no title)")),
        "url": item.get("url", ""),
        "snippet": strip_markup(item.get("description", "")).replace("\n", " "),
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
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        die(
            "BRAVE_API_KEY environment variable must be set. "
            "See the module docstring in web_search_brave.py for how to obtain one.",
            args.json,
        )

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
