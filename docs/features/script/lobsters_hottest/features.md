# Lobsters Hottest

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Lobsters JSON feeds (no API key): hottest.json for the front page, page/N.json for later pages.
- Use cli_utils.py's die(), positive_int and use_utf8_output().

## Actions

- Run as python3 lobsters_hottest.py from the repo root.
- Take:
    - How many discussions to return (default: 10).
    - {{Tags To Exclude}}: optional, repeatable, e.g. "meta".
- Retrieve the front pages, 25 stories a page, until there are 4 × that many candidates (at most 10 pages).
    - Stop early at an empty page.
    - Skip a story already seen on an earlier page.
- Leave out stories carrying an excluded tag, ignoring case.
- Rank the stories by score and keep the top ones.
- Output, one entry per discussion:
    - {{Rank}} {{Title}}
    - {{Score}} {{Number of Comments}} {{Posted Time}}, in UTC
    - {{Tags}}
    - {{Article Link}} (or the Lobsters thread for a text post) {{Discussion Link}}
    - With --json: an array of {rank, title, score, comments, posted, url, discussion_url, tags}.
- If no stories are found, say so.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
