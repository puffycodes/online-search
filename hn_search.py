#!/usr/bin/env python3
"""
Search past Hacker News stories and comments for a query, using the
Algolia Hacker News Search API (https://hn.algolia.com/api).

Unlike hottest_tech_discussions.py, which only sees the current front
page, this searches the whole HN archive: stories (or just Ask HN / Show
HN posts) or comments, ranked by relevance or newest first, optionally
limited to a date window, a minimum score, one author, or the comments of
one story's thread (--story, which pairs with hn_thread.py: that reads a
thread's top comments, this searches all of them). Words in the
query are matched whole, with no typo tolerance or prefix matching, so
"bun" doesn't also match "bundle" or "build".

No API key required.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import datetime as dt
import json
import re

import requests

from cli_utils import die, positive_int, use_utf8_output
from hn import TEXT_CHARS, clean_text, discussion_url, fetch_json, parse_item_id, posted_at

SEARCH_URL = "https://hn.algolia.com/api/v1/search"
SEARCH_BY_DATE_URL = "https://hn.algolia.com/api/v1/search_by_date"
RESULTS_TO_SHOW = 10
MAX_RESULTS = 100

# --type choice -> Algolia tag. Ask HN and Show HN posts are also stories.
TYPE_TAGS = {
    "story": "story",
    "comment": "comment",
    "ask": "ask_hn",
    "show": "show_hn",
}


def _day_start(day):
    """Unix time of 00:00 UTC on `day`."""
    return int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp())


def build_params(query, kind="story", since=None, until=None, min_points=None,
                 author=None, limit=RESULTS_TO_SHOW, story=None):
    """The Algolia query parameters for a search.

    `since` / `until` are inclusive dates (UTC days); `min_points` only
    applies to stories; `story` limits the search to one story's thread (it
    must be the story's id - a comment's id matches nothing). Typo tolerance
    and prefix matching are turned off so query words match whole words only.
    """
    tags = TYPE_TAGS[kind]
    if author:
        tags = f"{tags},author_{author}"
    if story:
        tags = f"{tags},story_{story}"
    filters = []
    if since:
        filters.append(f"created_at_i>={_day_start(since)}")
    if until:
        filters.append(f"created_at_i<{_day_start(until + dt.timedelta(days=1))}")
    if min_points is not None:
        filters.append(f"points>={min_points}")
    params = {
        "query": query,
        "tags": tags,
        "hitsPerPage": limit,
        "typoTolerance": "false",
        "queryType": "prefixNone",
    }
    if filters:
        params["numericFilters"] = ",".join(filters)
    return params


def search(query, kind="story", sort="relevance", since=None, until=None,
           min_points=None, author=None, limit=RESULTS_TO_SHOW, story=None):
    """Run a search; returns (hits, total_matches)."""
    url = SEARCH_BY_DATE_URL if sort == "date" else SEARCH_URL
    params = build_params(query, kind, since, until, min_points, author, limit, story)
    data = fetch_json(url, params)
    return data.get("hits") or [], data.get("nbHits", 0)


def hit_to_dict(rank, hit, max_chars=TEXT_CHARS):
    """Flatten an Algolia hit into the record used for both output modes.

    Stories: `url` is the linked article (or the HN thread for a self-post)
    and `text` the self-post body. Comments: `title` is the story the
    comment is on, `url` the comment's own HN page, `score` / `comments` are
    None, and `text` is the comment.
    """
    posted = posted_at({"time": hit.get("created_at_i", 0)})
    if "comment" in (hit.get("_tags") or []):
        story_id = hit.get("story_id")
        return {
            "rank": rank,
            "type": "comment",
            "title": hit.get("story_title") or "(no title)",
            "author": hit.get("author"),
            "posted": posted,
            "score": None,
            "comments": None,
            "url": discussion_url({"id": hit.get("objectID")}),
            "discussion_url": discussion_url({"id": story_id}) if story_id else None,
            "text": clean_text(hit.get("comment_text"), max_chars),
        }
    thread = discussion_url({"id": hit.get("objectID")})
    return {
        "rank": rank,
        "type": "story",
        "title": hit.get("title") or "(no title)",
        "author": hit.get("author"),
        "posted": posted,
        "score": hit.get("points") or 0,
        "comments": hit.get("num_comments") or 0,
        "url": hit.get("url") or thread,
        "discussion_url": thread,
        "text": clean_text(hit.get("story_text"), max_chars),
    }


def _indent(text, prefix="   "):
    return "\n".join(prefix + line if line else "" for line in text.splitlines())


def format_hit(row):
    """Render a record from hit_to_dict() as a text block."""
    if row["type"] == "comment":
        lines = [
            f"{row['rank']}. Comment by {row['author']} on \"{row['title']}\"",
            f"   Posted: {row['posted']}",
            f"   Comment: {row['url']}",
        ]
        if row["discussion_url"]:
            lines.append(f"   Discussion: {row['discussion_url']}")
    else:
        lines = [
            f"{row['rank']}. {row['title']}",
            f"   Score: {row['score']}  |  Comments: {row['comments']}  |  "
            f"Posted: {row['posted']}  |  By: {row['author']}",
            f"   Link: {row['url']}",
            f"   Discussion: {row['discussion_url']}",
        ]
    if row["text"]:
        lines.append("")
        lines.append(_indent(row["text"]))
    return "\n".join(lines)


def _date(value):
    """argparse type for a YYYY-MM-DD date."""
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}, expected YYYY-MM-DD")


def _item_id(value):
    try:
        return parse_item_id(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def _limit(value):
    """argparse type for --limit: 1 to MAX_RESULTS."""
    number = positive_int(value)
    if number > MAX_RESULTS:
        raise argparse.ArgumentTypeError(f"must be at most {MAX_RESULTS}, got {number}")
    return number


def _non_negative_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}")
    if number < 0:
        raise argparse.ArgumentTypeError(f"must be 0 or greater, got {number}")
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Search past Hacker News stories and comments."
    )
    parser.add_argument("query", help='Words to search for, e.g. "rust async"')
    parser.add_argument(
        "--type",
        choices=list(TYPE_TAGS),
        help="What to search: story (default), comment, ask (Ask HN) or show (Show HN)",
    )
    parser.add_argument(
        "--sort",
        choices=["relevance", "date"],
        default="relevance",
        help="relevance (default; best match, then score) or date (newest first)",
    )
    parser.add_argument("--since", type=_date, help="Only items posted on or after this UTC date, YYYY-MM-DD")
    parser.add_argument("--until", type=_date, help="Only items posted on or before this UTC date, YYYY-MM-DD")
    parser.add_argument(
        "--min-points",
        type=_non_negative_int,
        help="Only stories with at least this score (not for --type comment)",
    )
    parser.add_argument("--author", help="Only items posted by this HN username")
    parser.add_argument(
        "--story",
        type=_item_id,
        metavar="ITEM",
        help="Only comments in this story's thread: a story id or HN link (implies --type comment)",
    )
    parser.add_argument(
        "--limit",
        type=_limit,
        default=RESULTS_TO_SHOW,
        help=f"Number of results to return, 1-{MAX_RESULTS} (default: {RESULTS_TO_SHOW})",
    )
    parser.add_argument(
        "--max-chars",
        type=_non_negative_int,
        default=TEXT_CHARS,
        help=f"Cut comment / self-post text to this many characters, 0 for no limit (default: {TEXT_CHARS})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    args = parser.parse_args(argv)
    if not args.query.strip():
        parser.error("the search query must not be empty")
    if args.story:
        if args.type not in (None, "comment"):
            parser.error(f"--story searches a thread's comments; it can't be combined with --type {args.type}")
        args.type = "comment"
    args.type = args.type or "story"
    if args.since and args.until and args.until < args.since:
        parser.error("--until must not be before --since")
    if args.min_points is not None and args.type == "comment":
        parser.error("--min-points only applies to stories; comments have no score")
    if args.author is not None and not re.fullmatch(r"[A-Za-z0-9_-]+", args.author):
        parser.error(f"invalid HN username {args.author!r}")
    return args


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    if not args.json:
        print(f"Searching Hacker News for '{args.query}'...\n")

    try:
        hits, total = search(
            args.query,
            kind=args.type,
            sort=args.sort,
            since=args.since,
            until=args.until,
            min_points=args.min_points,
            author=args.author,
            limit=args.limit,
            story=args.story,
        )
    except (requests.RequestException, ValueError) as exc:
        die(str(exc), args.json)

    rows = [hit_to_dict(rank, hit, args.max_chars) for rank, hit in enumerate(hits, start=1)]

    if args.json:
        print(json.dumps({
            "query": args.query,
            "type": args.type,
            "sort": args.sort,
            "since": args.since.isoformat() if args.since else None,
            "until": args.until.isoformat() if args.until else None,
            "story": args.story,
            "total_matches": total,
            "results": rows,
        }, indent=2))
        return

    if not rows:
        print("No results found.")
        if args.story:
            print("(--story needs the story's id; a comment's id matches nothing.)")
        return

    if args.type == "comment":
        noun = "comment" if total == 1 else "comments"
    else:
        noun = "story" if total == 1 else "stories"
    where = f" in thread {args.story}" if args.story else ""
    print(f"{total} matching {noun}{where}; showing {len(rows)}, by {args.sort}.\n")
    for row in rows:
        print(format_hit(row))
        print()


if __name__ == "__main__":
    main()
