# Hottest Tech Discussions

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Hacker News API (no API key).
- Keep get_hottest_tech_discussions() and story_to_dict() importable, for stock_tech_buzz_agent.py and the hottest discussions web app.

## Actions

- Run as python3 hottest_tech_discussions.py from the repo root.
- Take:
    - How many discussions to return (default: 10).
- Retrieve HN's current top stories, and fetch the details of the first 4 × that many, 10 at a time.
    - Skip stories whose details fail to fetch, and anything that isn't a story (e.g. jobs).
- Rank the stories by score and keep the top ones.
- Output, one entry per discussion:
    - {{Rank}} {{Title}}
    - {{Score}} {{Number of Comments}} {{Posted Time}}
    - {{Article Link}} (or the HN thread when there is none) {{Discussion Link}}
    - With --json: an array of {rank, title, score, comments, posted, url, discussion_url}.
- If no stories are found, say so.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
