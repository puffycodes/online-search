#!/usr/bin/env python3
"""
Read one Hacker News thread: a story (or a comment) and its comments, in
the order HN ranks them, trimmed to a readable size.

The whole comment tree comes from the Algolia Hacker News API
(https://hn.algolia.com/api) in a single request, but Algolia lists
replies oldest first. HN's own ranked display order comes from the
official Hacker News API (https://github.com/HackerNews/API), whose
`kids` list for an item is in ranked order; it is fetched for the root
and for every comment whose replies are shown. If that fails for an
item, its replies fall back to oldest first and the result says so.

No API key required.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from cli_utils import die, positive_int, use_utf8_output
from hn import TEXT_CHARS, clean_text, discussion_url, fetch_json, fetch_story, posted_at

ITEM_URL = "https://hn.algolia.com/api/v1/items/{item_id}"
# A big thread is ~500 KB from Algolia and takes a few seconds.
ITEM_TIMEOUT = 30
TOP_COMMENTS = 20
REPLIES_PER_COMMENT = 3
DEPTH = 2
MAX_TOP_COMMENTS = 200
MAX_DEPTH = 10


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


def fetch_tree(item_id):
    """The item and its whole comment tree from Algolia, or None if there is no such item."""
    try:
        return fetch_json(ITEM_URL.format(item_id=item_id), timeout=ITEM_TIMEOUT)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise


def count_comments(node):
    """Number of comments below `node`, at any depth."""
    return sum(1 + count_comments(child) for child in node.get("children") or [])


def is_empty(node):
    """A deleted or dead comment with no replies, which isn't worth showing."""
    return not node.get("text") and not node.get("children")


def ranked_children(node, kids):
    """`node`'s children in HN's ranked order.

    `kids` is the item's `kids` list from the official HN API, or None if
    that couldn't be fetched (then Algolia's oldest-first order is kept).
    Children Algolia has but `kids` doesn't (e.g. very new ones) go last.
    """
    children = [child for child in node.get("children") or [] if not is_empty(child)]
    if kids is None:
        return children
    position = {kid: i for i, kid in enumerate(kids)}
    return sorted(children, key=lambda child: position.get(child.get("id"), len(position)))


def fetch_kids(item_ids):
    """{id: ranked kids list, or None if the item couldn't be fetched}, fetched 10 at a time."""
    item_ids = list(item_ids)
    with ThreadPoolExecutor(max_workers=10) as pool:
        items = list(pool.map(fetch_story, item_ids))
    return {
        item_id: ((item.get("kids") or []) if item is not None else None)
        for item_id, item in zip(item_ids, items)
    }


def select_comments(root, top=TOP_COMMENTS, replies=REPLIES_PER_COMMENT, depth=DEPTH):
    """Pick the comments to show: the first `top` top-level comments in
    ranked order, each with its first `replies` replies, down to `depth`
    levels (1 = top-level only).

    Fetches ranked order one level at a time, only for the comments whose
    replies will be shown. Returns (comments, ranked), where `comments` is
    a list of (node, level, shown_children) trees and `ranked` is False if
    any level fell back to oldest-first order.
    """
    kids = fetch_kids([root["id"]])
    ranked = kids[root["id"]] is not None
    level_nodes = ranked_children(root, kids[root["id"]])[:top]
    selected = {node["id"]: [] for node in level_nodes}
    roots = level_nodes

    for level in range(2, depth + 1):
        parents = [node for node in level_nodes if node.get("children")]
        if not parents or replies == 0:
            break
        kids = fetch_kids(node["id"] for node in parents)
        next_level = []
        for parent in parents:
            if kids[parent["id"]] is None:
                ranked = False
            chosen = ranked_children(parent, kids[parent["id"]])[:replies]
            selected[parent["id"]] = chosen
            for child in chosen:
                selected[child["id"]] = []
            next_level.extend(chosen)
        level_nodes = next_level

    def build(node, level):
        return (node, level, [build(child, level + 1) for child in selected.get(node["id"], [])])

    return [build(node, 1) for node in roots], ranked


def comment_to_dict(tree, max_chars=TEXT_CHARS):
    """Flatten a (node, level, shown_children) tree from select_comments()."""
    node, level, shown = tree
    replies = [child for child in node.get("children") or [] if not is_empty(child)]
    return {
        "id": node.get("id"),
        "author": node.get("author") or "[deleted]",
        "posted": posted_at({"time": node.get("created_at_i", 0)}),
        "depth": level,
        "url": discussion_url({"id": node.get("id")}),
        "text": clean_text(node.get("text"), max_chars) or "[deleted]",
        "reply_count": len(replies),
        "total_replies": count_comments(node),
        "replies": [comment_to_dict(child, max_chars) for child in shown],
    }


def thread_to_dict(root, comments, ranked, max_chars=TEXT_CHARS):
    """The record used for both output modes."""
    top_level = [child for child in root.get("children") or [] if not is_empty(child)]
    rows = [comment_to_dict(tree, max_chars) for tree in comments]
    story_id = root.get("story_id") or root.get("id")

    def shown(row):
        return 1 + sum(shown(reply) for reply in row["replies"])

    thread = discussion_url({"id": root.get("id")})
    return {
        "id": root.get("id"),
        "type": root.get("type"),
        "title": root.get("title"),
        "author": root.get("author"),
        "posted": posted_at({"time": root.get("created_at_i", 0)}),
        "score": root.get("points"),
        "url": root.get("url") or thread,
        "discussion_url": thread,
        "story_url": discussion_url({"id": story_id}),
        "text": clean_text(root.get("text"), max_chars),
        "total_comments": count_comments(root),
        "top_level_comments": len(top_level),
        "shown_comments": sum(shown(row) for row in rows),
        "ranked": ranked,
        "comments": rows,
    }


def _indent(text, prefix):
    return "\n".join(prefix + line if line else "" for line in text.splitlines())


def format_comment(row, number):
    pad = "   " * row["depth"]
    lines = [f"{pad}{number} {row['author']} | {row['posted']} | {row['url']}"]
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
    if thread["type"] == "comment":
        lines = [f"Comment by {thread['author']} | {thread['posted']}",
                 f"   Comment: {thread['discussion_url']}",
                 f"   Story: {thread['story_url']}"]
    else:
        lines = [
            thread["title"] or "(no title)",
            f"   Score: {thread['score']}  |  Comments: {thread['total_comments']}  |  "
            f"Posted: {thread['posted']}  |  By: {thread['author']}",
            f"   Link: {thread['url']}",
            f"   Discussion: {thread['discussion_url']}",
        ]
    if thread["text"]:
        lines.append("")
        lines.append(_indent(thread["text"], "   "))
    lines.append("")
    order = "HN's ranked order" if thread["ranked"] else "partly oldest-first (ranked order unavailable)"
    level = "direct replies" if thread["type"] == "comment" else "top-level"
    lines.append(
        f"Showing {thread['shown_comments']} of {thread['total_comments']} comments "
        f"({thread['top_level_comments']} {level}), in {order}."
    )
    for i, row in enumerate(thread["comments"], start=1):
        lines.append("")
        lines.append(format_comment(row, f"{i}."))
    return "\n".join(lines)


def _non_negative_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}")
    if number < 0:
        raise argparse.ArgumentTypeError(f"must be 0 or greater, got {number}")
    return number


def _bounded(maximum):
    def check(value):
        number = positive_int(value)
        if number > maximum:
            raise argparse.ArgumentTypeError(f"must be at most {maximum}, got {number}")
        return number
    return check


def _item_id(value):
    try:
        return parse_item_id(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Read a Hacker News thread: a story and its top comments."
    )
    parser.add_argument(
        "item",
        type=_item_id,
        help="HN item id or link, e.g. 48843352 or https://news.ycombinator.com/item?id=48843352",
    )
    parser.add_argument(
        "--top",
        type=_bounded(MAX_TOP_COMMENTS),
        default=TOP_COMMENTS,
        help=f"Top-level comments to show, 1-{MAX_TOP_COMMENTS} (default: {TOP_COMMENTS})",
    )
    parser.add_argument(
        "--replies",
        type=_non_negative_int,
        default=REPLIES_PER_COMMENT,
        help=f"Replies to show under each comment (default: {REPLIES_PER_COMMENT})",
    )
    parser.add_argument(
        "--depth",
        type=_bounded(MAX_DEPTH),
        default=DEPTH,
        help=f"Comment levels to show, 1 = top-level only, up to {MAX_DEPTH} (default: {DEPTH})",
    )
    parser.add_argument(
        "--max-chars",
        type=_non_negative_int,
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
        print(f"Reading Hacker News thread {args.item}...\n")

    try:
        root = fetch_tree(args.item)
        if root is None:
            die(f"No Hacker News item with id {args.item}.", args.json)
        comments, ranked = select_comments(root, args.top, args.replies, args.depth)
    except (requests.RequestException, ValueError) as exc:
        die(str(exc), args.json)

    thread = thread_to_dict(root, comments, ranked, args.max_chars)

    if args.json:
        print(json.dumps(thread, indent=2))
    else:
        print(format_thread(thread))


if __name__ == "__main__":
    main()
