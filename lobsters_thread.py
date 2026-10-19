#!/usr/bin/env python3
"""
Read one Lobsters thread: a story and its comments, in the order Lobsters
shows them, trimmed to a readable size.

The story and all its comments come from the story's JSON feed
(https://lobste.rs/s/<short id>.json) in a single request. Its comments
are one flat list, already in the site's display order (each comment
after its parent, siblings in Lobsters' own ranking), with a depth and a
parent id; this script nests them back into a tree. Like the front-page
feeds read by lobsters.py, it is public but not a documented API.

No API key required.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json
import re

import requests

from cli_utils import bounded_int, die, non_negative_int, use_utf8_output
from lobsters import HEADERS, LOBSTERS_BASE, posted_at

STORY_URL = f"{LOBSTERS_BASE}/s/{{story_id}}.json"
# A 250-comment thread is a few hundred KB.
STORY_TIMEOUT = 30
TOP_COMMENTS = 20
REPLIES_PER_COMMENT = 3
DEPTH = 2
MAX_TOP_COMMENTS = 200
MAX_DEPTH = 10
TEXT_CHARS = 600


def parse_story_id(value):
    """A story's short id from the id itself or a lobste.rs/s/<id>[/slug] link."""
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9]+", value):
        return value
    match = re.search(r"lobste\.rs/s/([A-Za-z0-9]+)", value)
    if match:
        return match.group(1)
    raise ValueError(
        f"expected a Lobsters story id or a lobste.rs/s/<id> link, got {value!r}"
    )


def fetch_story(story_id):
    """The story and its comments, or None if there is no such story."""
    response = requests.get(
        STORY_URL.format(story_id=story_id), headers=HEADERS, timeout=STORY_TIMEOUT
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    story = response.json()
    if not isinstance(story, dict):
        raise ValueError(f"unexpected response for story {story_id}: expected an object")
    return story


def username(user):
    """A user name from the feed, which gives a plain string (or, in older
    versions, an object with a `username`)."""
    if isinstance(user, dict):
        return user.get("username")
    return user


def clip(text, max_chars=TEXT_CHARS):
    """Tidy a comment / story text and cut it to `max_chars` characters with
    a trailing "..." (0 means no limit), or None if empty."""
    if not text:
        return None
    text = re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n")).strip()
    if not text:
        return None
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
    return text


def is_removed(comment):
    return bool(comment.get("is_deleted") or comment.get("is_moderated"))


def build_tree(comments):
    """Nest the flat comment list into [{"comment": raw, "children": [...]}],
    keeping its order. A comment whose parent isn't in the list goes at the top."""
    nodes, roots = {}, []
    for raw in comments:
        node = {"comment": raw, "children": []}
        nodes[raw.get("short_id")] = node
        parent = nodes.get(raw.get("parent_comment"))
        (parent["children"] if parent else roots).append(node)
    return roots


def prune(nodes):
    """Drop removed comments with no remaining replies, at any depth."""
    kept = []
    for node in nodes:
        node["children"] = prune(node["children"])
        if node["children"] or not is_removed(node["comment"]):
            kept.append(node)
    return kept


def count_comments(node):
    """Number of comments below `node`, at any depth."""
    return sum(1 + count_comments(child) for child in node["children"])


def comment_text(comment, max_chars=TEXT_CHARS):
    if comment.get("is_moderated"):
        return "[removed by a moderator]"
    if comment.get("is_deleted"):
        return "[deleted]"
    return clip(comment.get("comment_plain"), max_chars) or "[empty]"


def comment_to_dict(node, level, replies=REPLIES_PER_COMMENT, depth=DEPTH, max_chars=TEXT_CHARS):
    """Flatten one comment node, with its first `replies` replies down to `depth` levels."""
    raw = node["comment"]
    shown = node["children"][:replies] if level < depth else []
    return {
        "id": raw.get("short_id"),
        "author": username(raw.get("commenting_user")) or "[deleted]",
        "posted": posted_at(raw),
        "depth": level,
        "score": raw.get("score"),
        "url": raw.get("url") or raw.get("short_id_url"),
        "text": comment_text(raw, max_chars),
        "reply_count": len(node["children"]),
        "total_replies": count_comments(node),
        "replies": [comment_to_dict(child, level + 1, replies, depth, max_chars) for child in shown],
    }


def thread_to_dict(story, top=TOP_COMMENTS, replies=REPLIES_PER_COMMENT, depth=DEPTH,
                   max_chars=TEXT_CHARS):
    """The record used for both output modes."""
    roots = prune(build_tree(story.get("comments") or []))
    rows = [comment_to_dict(node, 1, replies, depth, max_chars) for node in roots[:top]]

    def shown(row):
        return 1 + sum(shown(reply) for reply in row["replies"])

    total = story.get("comment_count")
    discussion = story.get("comments_url") or story.get("short_id_url")
    return {
        "id": story.get("short_id"),
        "title": story.get("title"),
        "author": username(story.get("submitter_user")),
        "posted": posted_at(story),
        "score": story.get("score"),
        # A text post has url "", so fall back to its discussion page.
        "url": story.get("url") or discussion,
        "discussion_url": discussion,
        "tags": story.get("tags") or [],
        "text": clip(story.get("description_plain"), max_chars),
        "total_comments": total if total is not None else sum(1 + count_comments(n) for n in roots),
        "top_level_comments": len(roots),
        "shown_comments": sum(shown(row) for row in rows),
        "comments": rows,
    }


def _indent(text, prefix):
    return "\n".join(prefix + line if line else "" for line in text.splitlines())


def format_comment(row, number):
    pad = "   " * row["depth"]
    lines = [f"{pad}{number} {row['author']} | {row['score']} points | {row['posted']} | {row['url']}"]
    lines.append(_indent(row["text"], pad + "   "))
    for i, reply in enumerate(row["replies"], start=1):
        lines.append("")
        lines.append(format_comment(reply, f"{number}{i}."))
    hidden = row["reply_count"] - len(row["replies"])
    if hidden > 0:
        noun = "reply" if hidden == 1 else "replies"
        below = "comment" if row["total_replies"] == 1 else "comments"
        lines.append(
            f"{pad}   (+{hidden} more {noun}, {row['total_replies']} {below} below this one in all)"
        )
    return "\n".join(lines)


def format_thread(thread):
    """Render a thread_to_dict() record as a human-readable report."""
    lines = [
        thread["title"] or "(no title)",
        f"   Score: {thread['score']}  |  Comments: {thread['total_comments']}  |  "
        f"Posted: {thread['posted']}  |  By: {thread['author']}",
        f"   Tags: {', '.join(thread['tags']) or '(none)'}",
        f"   Link: {thread['url']}",
        f"   Discussion: {thread['discussion_url']}",
    ]
    if thread["text"]:
        lines.append("")
        lines.append(_indent(thread["text"], "   "))
    lines.append("")
    lines.append(
        f"Showing {thread['shown_comments']} of {thread['total_comments']} comments "
        f"({thread['top_level_comments']} top-level), in Lobsters' order."
    )
    for i, row in enumerate(thread["comments"], start=1):
        lines.append("")
        lines.append(format_comment(row, f"{i}."))
    return "\n".join(lines)


def _story_id(value):
    try:
        return parse_story_id(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Read a Lobsters thread: a story and its top comments."
    )
    parser.add_argument(
        "story",
        type=_story_id,
        help="Lobsters story id or link, e.g. ggpwfi or https://lobste.rs/s/ggpwfi",
    )
    parser.add_argument(
        "--top",
        type=bounded_int(MAX_TOP_COMMENTS),
        default=TOP_COMMENTS,
        help=f"Top-level comments to show, 1-{MAX_TOP_COMMENTS} (default: {TOP_COMMENTS})",
    )
    parser.add_argument(
        "--replies",
        type=non_negative_int,
        default=REPLIES_PER_COMMENT,
        help=f"Replies to show under each comment (default: {REPLIES_PER_COMMENT})",
    )
    parser.add_argument(
        "--depth",
        type=bounded_int(MAX_DEPTH),
        default=DEPTH,
        help=f"Comment levels to show, 1 = top-level only, up to {MAX_DEPTH} (default: {DEPTH})",
    )
    parser.add_argument(
        "--max-chars",
        type=non_negative_int,
        default=TEXT_CHARS,
        help=f"Cut each comment to this many characters, 0 for no limit (default: {TEXT_CHARS})",
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
        print(f"Reading Lobsters thread {args.story}...\n")

    try:
        story = fetch_story(args.story)
    except (requests.RequestException, ValueError) as exc:
        die(str(exc), args.json)

    if story is None:
        die(f"No Lobsters story with id {args.story}.", args.json)

    thread = thread_to_dict(story, args.top, args.replies, args.depth, args.max_chars)

    if args.json:
        print(json.dumps(thread, indent=2))
    else:
        print(format_thread(thread))


if __name__ == "__main__":
    main()
