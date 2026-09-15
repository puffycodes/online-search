#!/usr/bin/env python3
"""
Retrieve the top web search results for a query, using the Tavily
Search API: https://tavily.com/

Requires a TAVILY_API_KEY, set as an environment variable or in a .env
file in the current directory. Get one (free tier: 1,000 API credits/
month) by registering at https://app.tavily.com/

Real environment variables always take precedence over .env values.

(See web_search_brave.py's docstring for why Google's own Programmable
Search Engine and scraping DuckDuckGo's HTML were ruled out for those
scripts. Tavily is a different kind of option again: rather than
proxying Google's results like SerpApi/Serper, it crawls and ranks its
own index built specifically for LLM/agent consumption, so content
tends to be pre-cleaned and relevance-ranked rather than SEO-ranked.)

Tavily's API has no offset/page-based pagination - a single request
returns at most MAX_RESULTS_PER_REQUEST results, so --limit values
above that are silently capped rather than paginated across multiple
requests.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json
import os

import requests

from cli_utils import die, positive_int

SEARCH_URL = "https://api.tavily.com/search"
REQUEST_TIMEOUT = 10

RESULTS_TO_SHOW = 10
# Tavily's documented cap on max_results per request; there is no
# pagination parameter, so this is also the hard ceiling on --limit.
MAX_RESULTS_PER_REQUEST = 20

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_dotenv(path=ENV_FILE):
    """Populate os.environ from a simple KEY=VALUE .env file.

    Existing environment variables are never overwritten, so real env
    vars always take precedence over .env values. Missing files are
    silently ignored.
    """
    try:
        with open(path, encoding="utf-8") as env_file:
            lines = env_file.readlines()
    except FileNotFoundError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def fetch_results(query, limit, api_key):
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": min(limit, MAX_RESULTS_PER_REQUEST),
    }
    response = requests.post(SEARCH_URL, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return data.get("results", [])[:limit]


def result_to_dict(rank, item):
    """Flatten a raw API result into the record used for both output modes."""
    return {
        "rank": rank,
        "title": item.get("title", "(no title)"),
        "url": item.get("url", ""),
        "snippet": item.get("content", "").replace("\n", " "),
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
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        die(
            "TAVILY_API_KEY environment variable must be set. "
            "See the module docstring in web_search_tavily.py for how to obtain one.",
            args.json,
        )

    if not args.json:
        print(f"Searching for: {args.query}\n")

    try:
        items = fetch_results(args.query, args.limit, api_key)
    except requests.RequestException as exc:
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
