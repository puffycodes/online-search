# Hacker News Search

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Algolia Hacker News Search API (no API key).
- Use hn.py's fetch_json(), clean_text(), parse_item_id(), discussion_url() and posted_at(), so links, times and text look the same as in the other HN scripts.

## Actions

- Run as python3 hn_search.py from the repo root.
- Take:
    - {{Query}}: the words to search for; must not be empty.
    - What to search: stories (default), comments, Ask HN posts or Show HN posts.
    - The order: by relevance (default; best match, then score) or by date (newest first).
    - An optional {{Since}} and {{Until}} date (YYYY-MM-DD, inclusive, UTC).
    - An optional minimum score, for stories only.
    - An optional HN {{Author}} username.
    - An optional {{Story}}: a story's id or HN link, to search only the comments in its thread; this implies a comment search.
    - --include-job-threads, to keep HN's monthly job threads, which are left out by default.
    - How many results to return (default: 10, at most 100).
    - How many characters of comment / self-post text to keep (default: 600; 0 for all).
- Reject the options, before any network call, when:
    - The query is empty, a date is invalid, or {{Until}} is before {{Since}}.
    - A minimum score is given for a comment search.
    - {{Story}} isn't an id or HN item link, or is combined with a non-comment search.
    - The number of results is not 1-100, or the author isn't a valid HN username.
- Match query words as whole words only: no typo tolerance and no prefix matching ("bun" must not match "bundle").
- Leave out HN's monthly job threads ("Ask HN: Who is hiring?", "Who wants to be hired?", "Freelancer? Seeking freelancer?", in any capitalisation and including the older "Freelancers?" wording) and their comments, unless --include-job-threads is given or {{Story}} is searched:
    - Find the job threads among the results by title, exclude them from the search by id, and search again, until a page has none or after 5 searches.
    - Drop any job-thread results still left, even if fewer than the number asked for remain.
    - Report {{Job Threads Skipped}}.
- Output:
    - {{Total Matches}} (in thread {{Story}}, if given), and how many are shown.
    - "Left out {{Job Threads Skipped}} job threads", when any were.
    - For each story: {{Rank}} {{Title}} {{Score}} {{Number of Comments}} {{Posted Time}} {{Author}} {{Article Link}} (or the HN thread for a self-post) {{Discussion Link}} and the self-post's text, if any.
    - For each comment: {{Rank}} {{Author}} {{Story Title}} {{Posted Time}} {{Comment Link}} {{Discussion Link}} {{Comment Text}}.
    - Text is converted from HTML to plain text and cut to the character limit with "...".
    - With --json: {query, type, sort, since, until, story, total_matches, job_threads_skipped, results: [{rank, type, title, author, posted, score, comments, url, discussion_url, text}]}; for a comment, title is the story's, url the comment's own page, and score and comments are null.
- If nothing matches, say so; with {{Story}}, add that it must be the story's id, as a comment's id matches nothing.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without. When the API rejects a request, its message is the error.
    - An invalid option value exits with code 2, before any network call.
