#!/usr/bin/env python3
"""
List the hottest discussions on Lobsters (https://lobste.rs/) right now,
using the site's JSON feeds: the front page (hottest.json) and its later
pages (page/N.json). These feeds are public but not a documented API, so
they could change without notice.

No API key required.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json
import math
from datetime import datetime, timezone

import requests

from cli_utils import die, positive_int, use_utf8_output

LOBSTERS_BASE = "https://lobste.rs"
HOTTEST_URL = f"{LOBSTERS_BASE}/hottest.json"
# hottest.json ignores ?page=N; later front pages live at page/N.json.
PAGE_URL = f"{LOBSTERS_BASE}/page/{{page}}.json"
HEADERS = {"User-Agent": "online-search/1.0 (lobsters_hottest.py)"}
REQUEST_TIMEOUT = 10

STORIES_PER_PAGE = 25
# Same idea as hottest_tech_discussions.py: Lobsters already orders its
# front page by its own hotness (score + age decay), so ranking the first
# 4x by score is enough to surface the top N by score (40 for the default
# 10, i.e. 2 pages). MAX_PAGES caps the requests for a very large --limit.
CANDIDATE_POOL_FACTOR = 4
MAX_PAGES = 10
RESULTS_TO_SHOW = 10


def fetch_page(page):
    """One front page of stories (page 1 is hottest.json), as a list."""
    url = HOTTEST_URL if page == 1 else PAGE_URL.format(page=page)
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    stories = response.json()
    if not isinstance(stories, list):
        raise ValueError(f"unexpected response from {url}: expected a list of stories")
    return stories


def get_lobsters_hottest(limit=RESULTS_TO_SHOW, exclude_tags=()):
    """The top `limit` stories by score among the front pages' first
    limit x CANDIDATE_POOL_FACTOR, leaving out any story carrying one of
    `exclude_tags`."""
    pool_size = max(limit, 0) * CANDIDATE_POOL_FACTOR
    pages = min(math.ceil(pool_size / STORIES_PER_PAGE), MAX_PAGES)

    pool, seen = [], set()
    for page in range(1, pages + 1):
        stories = fetch_page(page)
        if not stories:
            break
        for story in stories:
            # The front page can shift between requests, repeating a story.
            if story.get("short_id") in seen:
                continue
            seen.add(story.get("short_id"))
            pool.append(story)
    pool = pool[:pool_size]

    excluded = {tag.lower() for tag in exclude_tags}
    pool = [s for s in pool if not excluded & set(s.get("tags") or [])]
    pool.sort(key=lambda s: s.get("score", 0), reverse=True)
    return pool[:limit]


def posted_at(story):
    """Story submission time as a 'YYYY-MM-DD HH:MM UTC' string (Lobsters
    gives local time with an offset), or None if missing or unreadable."""
    try:
        created = datetime.fromisoformat(story["created_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return created.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def story_to_dict(rank, story):
    """Flatten a raw Lobsters story into the record used for both output modes."""
    discussion_url = story.get("comments_url") or story.get("short_id_url")
    return {
        "rank": rank,
        "title": story.get("title", "(no title)"),
        "score": story.get("score", 0),
        "comments": story.get("comment_count", 0),
        "posted": posted_at(story),
        # A text post has url "", so fall back to its discussion page.
        "url": story.get("url") or discussion_url,
        "discussion_url": discussion_url,
        "tags": story.get("tags") or [],
    }


def format_story(row):
    """Render a story record from story_to_dict() as a text block."""
    lines = [
        f"{row['rank']}. {row['title']}",
        f"   Score: {row['score']}  |  Comments: {row['comments']}  |  Posted: {row['posted']}",
        f"   Tags: {', '.join(row['tags']) or '(none)'}",
        f"   Link: {row['url']}",
        f"   Discussion: {row['discussion_url']}",
    ]
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="List the hottest discussions on Lobsters."
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=RESULTS_TO_SHOW,
        help=f"Number of stories to return (default: {RESULTS_TO_SHOW})",
    )
    parser.add_argument(
        "--exclude-tag",
        action="append",
        default=[],
        metavar="TAG",
        help='Leave out stories with this tag, e.g. "meta" for site announcements. Repeatable.',
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    if not args.json:
        print("Fetching the hottest discussions from Lobsters...\n")

    try:
        stories = get_lobsters_hottest(limit=args.limit, exclude_tags=args.exclude_tag)
    except (requests.RequestException, ValueError) as exc:
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
