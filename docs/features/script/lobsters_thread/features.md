# Lobsters Thread

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Lobsters story JSON feed (no API key): lobste.rs/s/{{Story}}.json, the story and all its comments in one request.
- Use lobsters.py's posted_at(), HEADERS and LOBSTERS_BASE.
- Use cli_utils.py's die(), bounded_int, non_negative_int and use_utf8_output().

## Actions

- Run as python3 lobsters_thread.py from the repo root.
- Take:
    - {{Story}}: a Lobsters story short id or a lobste.rs/s/<id> link.
    - How many top-level comments to show (default: 20, at most 200).
    - How many replies to show under each shown comment (default: 3; 0 for none).
    - How many comment levels to show (default: 2, top-level and replies; at most 10).
    - How many characters of each comment to keep (default: 600; 0 for all).
- Reject the options, before any network call, when the story isn't a short id or lobste.rs/s/ link, or a number is out of range.
- Retrieve the story and its comments in one request.
    - If there is no such story, fail with "No Lobsters story with id {{Story}}."
- Nest the flat comment list into a tree, keeping Lobsters' display order.
- Leave out deleted or moderated comments with no remaining replies, at any depth; show one that has replies as "[deleted]" or "[removed by a moderator]".
- Output:
    - {{Title}} {{Score}} {{Total Comments}} {{Posted Time}} {{Author}} {{Tags}} {{Article Link}} (or the thread for a text post) {{Discussion Link}}, and the text post's body if any.
    - How many comments are shown, of how many, and how many are top-level.
    - Each shown comment, indented and numbered by position (1., 1.1., ...): {{Author}} {{Score}} {{Posted Time}} {{Comment Link}} {{Comment Text}}.
    - Under a comment with replies left out: how many more replies, and how many comments below it in all.
    - With --json: {id, title, author, posted, score, url, discussion_url, tags, text, total_comments, top_level_comments, shown_comments, comments: [{id, author, posted, depth, score, url, text, reply_count, total_replies, replies: [...]}]}.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
