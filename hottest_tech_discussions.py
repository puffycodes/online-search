#!/usr/bin/env python3
"""
List the hottest technology discussions right now, from one or more
sources: Hacker News (the public API, https://github.com/HackerNews/API)
and Lobsters (https://lobste.rs/, its front-page JSON feeds). Hacker News
is the default.

Each source is ranked on its own and reported in its own section: their
scores aren't comparable (Lobsters is much smaller), so stories from
different sources are never ranked against each other, and the same story
on both sites is never combined into one entry.

No API key required.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json

import requests

import hn
import lobsters
from cli_utils import die, positive_int, use_utf8_output

# Output order, whatever order the sources were asked for.
SOURCES = ("hn", "lobsters")
SOURCE_NAMES = {"hn": "Hacker News", "lobsters": "Lobsters"}
DEFAULT_SOURCES = ("hn",)
RESULTS_TO_SHOW = 10


def get_hottest_tech_discussions(limit=RESULTS_TO_SHOW):
    """The top `limit` Hacker News stories, as raw HN items. Hacker News
    only, for stock_tech_buzz_agent.py and the hottest discussions web app."""
    return hn.fetch_hottest(limit)


def story_to_dict(rank, story):
    """Flatten a raw HN story into the record used for both output modes."""
    return {
        "rank": rank,
        "title": story.get("title", "(no title)"),
        "score": story.get("score", 0),
        "comments": story.get("descendants", 0),
        "posted": hn.posted_at(story),
        "url": story.get("url") or hn.discussion_url(story),
        "discussion_url": hn.discussion_url(story),
        "tags": [],
        "source": "hn",
    }


def lobsters_story_to_dict(rank, story):
    """Flatten a raw Lobsters story into the record used for both output modes."""
    discussion_url = story.get("comments_url") or story.get("short_id_url")
    return {
        "rank": rank,
        "title": story.get("title", "(no title)"),
        "score": story.get("score", 0),
        "comments": story.get("comment_count", 0),
        "posted": lobsters.posted_at(story),
        # A text post has url "", so fall back to its discussion page.
        "url": story.get("url") or discussion_url,
        "discussion_url": discussion_url,
        "tags": story.get("tags") or [],
        "source": "lobsters",
    }


class SourceError(Exception):
    """One source's fetch failed; the message names the source."""

    def __init__(self, source, error):
        super().__init__(f"{SOURCE_NAMES[source]}: {error}")
        self.source = source


def get_rows(sources, limit=RESULTS_TO_SHOW, exclude_tags=()):
    """{source: [record, ...]} for each of `sources`, in SOURCES order,
    each ranked from 1 within its source. The first source to fail raises
    SourceError, so no partial result is returned."""
    rows = {}
    for source in SOURCES:
        if source not in sources:
            continue
        try:
            if source == "hn":
                stories = get_hottest_tech_discussions(limit=limit)
                to_dict = story_to_dict
            else:
                stories = lobsters.fetch_hottest(limit, exclude_tags=exclude_tags)
                to_dict = lobsters_story_to_dict
        except (requests.RequestException, ValueError) as exc:
            raise SourceError(source, exc) from exc
        rows[source] = [to_dict(rank, s) for rank, s in enumerate(stories, start=1)]
    return rows


def format_story(row):
    """Render a story record as a text block (with a Tags line for Lobsters)."""
    lines = [
        f"{row['rank']}. {row['title']}",
        f"   Score: {row['score']}  |  Comments: {row['comments']}  |  Posted: {row['posted']}",
    ]
    if row.get("source") == "lobsters":
        lines.append(f"   Tags: {', '.join(row['tags']) or '(none)'}")
    lines += [
        f"   Link: {row['url']}",
        f"   Discussion: {row['discussion_url']}",
    ]
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="List the hottest technology discussions on Hacker News and/or Lobsters."
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=SOURCES,
        metavar="SOURCE",
        help="Where to look: hn (Hacker News) or lobsters. Repeatable, one section "
             "per source (default: hn)",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=RESULTS_TO_SHOW,
        help=f"Number of stories to return from each source (default: {RESULTS_TO_SHOW})",
    )
    parser.add_argument(
        "--exclude-tag",
        action="append",
        default=[],
        metavar="TAG",
        help='Leave out Lobsters stories with this tag, e.g. "meta" for site '
             "announcements. Repeatable; needs --source lobsters.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    args = parser.parse_args(argv)
    # A repeated source counts once, and the output order is fixed.
    asked = args.source or DEFAULT_SOURCES
    args.source = [s for s in SOURCES if s in asked]
    if args.exclude_tag and "lobsters" not in args.source:
        parser.error("--exclude-tag needs --source lobsters (Hacker News stories have no tags)")
    return args


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    if not args.json:
        names = " and ".join(SOURCE_NAMES[s] for s in args.source)
        print(f"Fetching the hottest technology discussions from {names}...\n")

    try:
        rows = get_rows(args.source, limit=args.limit, exclude_tags=args.exclude_tag)
    except SourceError as exc:
        die(str(exc), args.json)

    if args.json:
        print(json.dumps([row for source in rows for row in rows[source]], indent=2))
        return

    # With Hacker News alone, the report is the same as before Lobsters was added.
    headings = args.source != ["hn"]
    for source, source_rows in rows.items():
        if headings:
            name = SOURCE_NAMES[source]
            print(f"{name}\n{'=' * len(name)}\n")
        if not source_rows:
            print("No stories found.")
            if headings:
                print()
            continue
        for row in source_rows:
            print(format_story(row))
            print()


if __name__ == "__main__":
    main()
