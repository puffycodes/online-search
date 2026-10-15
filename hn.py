#!/usr/bin/env python3
"""
Shared Hacker News helpers for hottest_tech_discussions.py, hn_search.py
and hn_thread.py: JSON fetching (surfacing the Algolia API's own error
message), fetching one item from the official Hacker News API
(https://github.com/HackerNews/API), reading an item id from a number or
an HN link, the item's HN page link, its posting time, and converting HN's
HTML comment / self-post text to plain text.

Not a CLI itself - this module is imported, not run.
"""

import html
import re
from datetime import datetime, timezone

import requests

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HN_ITEM_URL = f"{HN_API_BASE}/item/{{item_id}}.json"
REQUEST_TIMEOUT = 10
TEXT_CHARS = 600


def fetch_json(url, params=None, timeout=REQUEST_TIMEOUT):
    """GET `url` and return its JSON body, raising requests.HTTPError on an error status."""
    response = requests.get(url, params=params, timeout=timeout)
    if not response.ok:
        # Algolia explains a rejected request as {"message": "...", "status": 400};
        # surface that rather than a bare "400 Client Error".
        try:
            message = response.json().get("message")
        except (ValueError, AttributeError):
            message = None
        if message:
            raise requests.HTTPError(f"{response.status_code}: {message}", response=response)
    response.raise_for_status()
    return response.json()


def fetch_story(item_id):
    """One item from the official HN API, or None if it can't be fetched.

    Failures are swallowed so one bad item doesn't sink a batch. The API
    returns `null` (None) for an item that doesn't exist.
    """
    try:
        return fetch_json(HN_ITEM_URL.format(item_id=item_id))
    except (requests.RequestException, ValueError):
        return None


def parse_item_id(value):
    """An HN item id from a number or a news.ycombinator.com/item?id=N URL."""
    value = value.strip()
    if value.isdigit():
        return int(value)
    match = re.search(r"news\.ycombinator\.com/item\?(?:.*&)?id=(\d+)", value)
    if match:
        return int(match.group(1))
    raise ValueError(
        f"expected an HN item id or a news.ycombinator.com/item?id=N link, got {value!r}"
    )


def discussion_url(story):
    """The Hacker News comments page for a story/item."""
    return f"https://news.ycombinator.com/item?id={story['id']}"


def posted_at(story):
    """Story submission time as a 'YYYY-MM-DD HH:MM UTC' string."""
    return datetime.fromtimestamp(story.get("time", 0), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


def clean_text(raw, max_chars=TEXT_CHARS):
    """Plain text from an HN comment / self-post body (HTML), or None if empty.

    Paragraph tags become blank lines, other tags are dropped (a link keeps
    its visible text), entities are decoded, and the result is cut to
    `max_chars` characters with a trailing "..." (0 means no limit).
    """
    if not raw:
        return None
    text = re.sub(r"<p>", "\n\n", raw)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return None
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
    return text
