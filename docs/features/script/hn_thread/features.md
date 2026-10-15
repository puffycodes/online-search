# Hacker News Thread

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Algolia Hacker News API (no API key) for the comment tree, and the official Hacker News API (no API key) for HN's ranked comment order.
- Use hn.py's fetch_json(), fetch_story(), clean_text(), discussion_url() and posted_at().

## Actions

- Run as python3 hn_thread.py from the repo root.
- Take:
    - {{Item}}: an HN item id or a news.ycombinator.com/item?id=N link; usually a story, or a comment to read it and its replies.
    - How many top-level comments to show (default: 20, at most 200).
    - How many replies to show under each shown comment (default: 3; 0 for none).
    - How many comment levels to show (default: 2, top-level and replies; at most 10).
    - How many characters of each comment to keep (default: 600; 0 for all).
- Reject the options, before any network call, when the item isn't an id or HN item link, or a number is out of range.
- Retrieve the item and its whole comment tree in one request.
    - If there is no such item, fail with "No Hacker News item with id {{Item}}."
- Order each shown comment's replies the way HN ranks them, fetching the ranked order only for the comments whose replies are shown.
    - If the ranked order can't be fetched for a comment, keep its replies oldest first and say the order is partly oldest-first.
- Leave out deleted or dead comments with no replies; show one that has replies as "[deleted]".
- Output:
    - {{Title}} {{Score}} {{Total Comments}} {{Posted Time}} {{Author}} {{Article Link}} {{Discussion Link}}, and the self-post text if any; for a comment, its author, time, text, link and its story's link.
    - How many comments are shown, of how many, and how many are top-level.
    - Each shown comment, indented and numbered by position (1., 1.1., ...): {{Author}} {{Posted Time}} {{Comment Link}} {{Comment Text}}.
    - Under a comment with replies left out: how many more replies, and how many comments below it in all.
    - With --json: {id, type, title, author, posted, score, url, discussion_url, story_url, text, total_comments, top_level_comments, shown_comments, ranked, comments: [{id, author, posted, depth, url, text, reply_count, total_replies, replies: [...]}]}.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
