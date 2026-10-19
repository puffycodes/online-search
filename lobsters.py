#!/usr/bin/env python3
"""
Shared Lobsters (https://lobste.rs/) helpers for hottest_tech_discussions.py
and lobsters_thread.py: the site's base URL and request headers, fetching
the hottest stories from its front-page JSON feeds (hottest.json and its
later pages, page/N.json), and a story's posting time in UTC. These feeds
are public but not a documented API, so they could change without notice.

Not a CLI itself - this module is imported, not run.
"""

import math
from datetime import datetime, timezone

import requests

LOBSTERS_BASE = "https://lobste.rs"
HOTTEST_URL = f"{LOBSTERS_BASE}/hottest.json"
# hottest.json ignores ?page=N; later front pages live at page/N.json.
PAGE_URL = f"{LOBSTERS_BASE}/page/{{page}}.json"
HEADERS = {"User-Agent": "online-search/1.0 (lobsters.py)"}
REQUEST_TIMEOUT = 10

STORIES_PER_PAGE = 25
# Same idea as hn.fetch_hottest(): Lobsters already orders its front page
# by its own hotness (score + age decay), so ranking the first 4x by score
# is enough to surface the top N by score (40 for the default 10, i.e. 2
# pages). MAX_PAGES caps the requests for a very large limit.
CANDIDATE_POOL_FACTOR = 4
MAX_PAGES = 10


def fetch_page(page):
    """One front page of stories (page 1 is hottest.json), as a list."""
    url = HOTTEST_URL if page == 1 else PAGE_URL.format(page=page)
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    stories = response.json()
    if not isinstance(stories, list):
        raise ValueError(f"unexpected response from {url}: expected a list of stories")
    return stories


def fetch_hottest(limit, exclude_tags=()):
    """The top `limit` stories by score among the front pages' first
    limit x CANDIDATE_POOL_FACTOR, leaving out any story carrying one of
    `exclude_tags` (ignoring case)."""
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
