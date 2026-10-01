#!/usr/bin/env python3
"""
Get a synthesized, cited answer to a query, using the Perplexity Sonar
API: https://docs.perplexity.ai/

Requires a PERPLEXITY_API_KEY, set as an environment variable or in a
.env file in the current directory. Get one from your account's API
settings at https://www.perplexity.ai/settings/api. Unlike the other
engines in this repo, Perplexity's API has no ongoing free tier -
billing must be set up on the account (new accounts sometimes get a
small one-time credit).

Real environment variables always take precedence over .env values.

Unlike web_search_brave.py, web_search_serpapi.py, web_search_serper.py,
web_search_tavily.py, and web_search_exa.py, Sonar models don't return
a ranked list of independent search results - they run their own web
search internally and return one synthesized natural-language answer,
plus the list of sources it drew on. This script's output shape
reflects that: an "answer" string plus a "sources" list of
{rank, title, url, date}, not the flat [{rank, title, url, snippet}, ...]
array the other five scripts share. Code consuming this script (e.g.
an agent) needs to handle that difference rather than assuming a
uniform interface across all web_search_*.py scripts.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json

import requests

from cli_utils import die, load_dotenv, positive_int, require_env

SEARCH_URL = "https://api.perplexity.ai/chat/completions"
# Sonar answers take noticeably longer than a plain search-results
# lookup, since the model synthesizes the answer before responding.
REQUEST_TIMEOUT = 30

DEFAULT_MODEL = "sonar"
SOURCES_TO_SHOW = 10


def fetch_answer(query, api_key, model=DEFAULT_MODEL):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": query}],
    }
    response = requests.post(
        SEARCH_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise requests.RequestException("Perplexity returned no answer.")

    answer = choices[0].get("message", {}).get("content") or ""
    if not answer.strip():
        raise requests.RequestException("Perplexity returned no answer.")
    sources = data.get("search_results") or []
    return answer, sources


def source_to_dict(rank, item):
    """Flatten a raw citation into the record used for both output modes."""
    return {
        "rank": rank,
        "title": item.get("title", "(no title)"),
        "url": item.get("url", ""),
        "date": item.get("date"),
    }


def format_answer(answer, sources):
    """Render an answer plus its source list as a human-readable block."""
    lines = [answer.strip()]
    if sources:
        lines.append("")
        lines.append("Sources:")
        for row in sources:
            suffix = f" ({row['date']})" if row.get("date") else ""
            lines.append(f"  {row['rank']}. {row['title']}{suffix}")
            lines.append(f"     {row['url']}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Get a synthesized, cited answer to a query."
    )
    parser.add_argument("query", help="Question or search query")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Perplexity Sonar model id (default: {DEFAULT_MODEL}), "
        "e.g. sonar, sonar-pro, sonar-reasoning, sonar-reasoning-pro",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=SOURCES_TO_SHOW,
        help=f"Max number of sources to display (default: {SOURCES_TO_SHOW}); "
        "Perplexity itself decides how many sources to cite, this only "
        "trims that list locally.",
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
    api_key = require_env("PERPLEXITY_API_KEY", "web_search_perplexity.py", args.json)

    if not args.json:
        print(f"Asking: {args.query}\n")

    try:
        answer, raw_sources = fetch_answer(args.query, api_key, args.model)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    sources = [
        source_to_dict(rank, item)
        for rank, item in enumerate(raw_sources[: args.limit], start=1)
    ]

    if args.json:
        print(json.dumps({"answer": answer, "sources": sources}, indent=2))
        return

    print(format_answer(answer, sources))


if __name__ == "__main__":
    main()
