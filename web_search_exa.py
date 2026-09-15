#!/usr/bin/env python3
"""
Retrieve the top web search results for a query, using the Exa Search
API: https://exa.ai/

Requires an EXA_API_KEY, set as an environment variable or in a .env
file in the current directory. Get one (free tier: $10 of monthly
search credit) by registering at https://dashboard.exa.ai/

Real environment variables always take precedence over .env values.

(See web_search_brave.py's docstring for why Google's own Programmable
Search Engine and scraping DuckDuckGo's HTML were ruled out for those
scripts. Exa is a different kind of option again: instead of keyword-
matching or proxying Google, it runs a neural/semantic search index -
built for "find pages like this idea" queries as much as exact keyword
matches - so ranking and results can differ meaningfully from a
traditional keyword search engine.)

Exa's API has no offset/page-based pagination - a single request
returns at most MAX_RESULTS_PER_REQUEST results, so --limit values
above that are silently capped rather than paginated across multiple
requests.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import os

import requests

from cli_utils import die, load_dotenv, positive_int, print_results

SEARCH_URL = "https://api.exa.ai/search"
REQUEST_TIMEOUT = 10

RESULTS_TO_SHOW = 10
# Exa's documented cap on numResults per request; there is no
# pagination parameter, so this is also the hard ceiling on --limit.
MAX_RESULTS_PER_REQUEST = 100
# Exa can return full page text; ask it to truncate each result's
# "text" field to a snippet-sized excerpt server-side.
SNIPPET_MAX_CHARACTERS = 300


def fetch_results(query, limit, api_key):
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "numResults": min(limit, MAX_RESULTS_PER_REQUEST),
        "contents": {
            "text": {"maxCharacters": SNIPPET_MAX_CHARACTERS, "includeHtmlTags": False}
        },
    }
    response = requests.post(
        SEARCH_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()
    return data.get("results", [])[:limit]


def result_to_dict(rank, item):
    """Flatten a raw API result into the record used for both output modes."""
    return {
        "rank": rank,
        "title": item.get("title", "(no title)"),
        "url": item.get("url", ""),
        "snippet": (item.get("text") or "").replace("\n", " "),
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
        help=f"Number of results to return (default: {RESULTS_TO_SHOW}, "
        f"capped at {MAX_RESULTS_PER_REQUEST})",
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
    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        die(
            "EXA_API_KEY environment variable must be set. "
            "See the module docstring in web_search_exa.py for how to obtain one.",
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
