#!/usr/bin/env python3
"""
List the hottest technology discussions right now, using the
Hacker News public API (https://github.com/HackerNews/API).

No API key required.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from cli_utils import die, positive_int

HN_BASE = "https://hacker-news.firebaseio.com/v0"
TOP_STORIES_URL = f"{HN_BASE}/topstories.json"
ITEM_URL = f"{HN_BASE}/item/{{item_id}}.json"

# How many of the current top stories to inspect per requested result,
# before ranking them by score. HN's topstories list is already ranked by
# its own "hotness" algorithm (score + age decay), so pulling details for
# the first 4x is enough to reliably surface the top N by score (40 for
# the default 10), and it scales so --limit 50 isn't capped at a fixed pool.
CANDIDATE_POOL_FACTOR = 4
RESULTS_TO_SHOW = 10
REQUEST_TIMEOUT = 10


def fetch_json(url):
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_story(item_id):
    try:
        return fetch_json(ITEM_URL.format(item_id=item_id))
    except (requests.RequestException, ValueError):
        return None


def get_hottest_tech_discussions(limit=RESULTS_TO_SHOW):
    story_ids = fetch_json(TOP_STORIES_URL)[:max(limit, 0) * CANDIDATE_POOL_FACTOR]

    with ThreadPoolExecutor(max_workers=10) as pool:
        stories = list(pool.map(fetch_story, story_ids))

    stories = [s for s in stories if s and s.get("type") == "story"]
    stories.sort(key=lambda s: s.get("score", 0), reverse=True)
    return stories[:limit]


def discussion_url(story):
    """The Hacker News comments page for a story/item."""
    return f"https://news.ycombinator.com/item?id={story['id']}"


def posted_at(story):
    """Story submission time as a 'YYYY-MM-DD HH:MM UTC' string."""
    return datetime.fromtimestamp(story.get("time", 0), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


def story_to_dict(rank, story):
    """Flatten a raw HN story into the record used for both output modes."""
    return {
        "rank": rank,
        "title": story.get("title", "(no title)"),
        "score": story.get("score", 0),
        "comments": story.get("descendants", 0),
        "posted": posted_at(story),
        "url": story.get("url") or discussion_url(story),
        "discussion_url": discussion_url(story),
    }


def format_story(row):
    """Render a story record from story_to_dict() as a text block."""
    lines = [
        f"{row['rank']}. {row['title']}",
        f"   Score: {row['score']}  |  Comments: {row['comments']}  |  Posted: {row['posted']}",
        f"   Link: {row['url']}",
        f"   Discussion: {row['discussion_url']}",
    ]
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="List the hottest technology discussions on Hacker News."
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=RESULTS_TO_SHOW,
        help=f"Number of stories to return (default: {RESULTS_TO_SHOW})",
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
        print("Fetching the hottest technology discussions from Hacker News...\n")

    try:
        stories = get_hottest_tech_discussions(limit=args.limit)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    rows = [story_to_dict(rank, s) for rank, s in enumerate(stories, start=1)]

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    if not rows:
        print("No stories found.")
        return

    for row in rows:
        print(format_story(row))
        print()


if __name__ == "__main__":
    main()
