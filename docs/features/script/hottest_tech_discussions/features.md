# Hottest Tech Discussions

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Take the discussions from one or more sources, each without an API key:
    - Hacker News (hn): the Hacker News API.
    - Lobsters (lobsters): the Lobsters JSON feeds, hottest.json for the front page and page/N.json for later pages.
- Keep each source's fetching in its shared module, so other scripts can reuse it:
    - hn.py: fetch_json(), fetch_story(), discussion_url(), posted_at(), and the hottest-stories fetch.
    - lobsters.py: the hottest-stories fetch, posted_at(), HEADERS and LOBSTERS_BASE (also used by lobsters_thread.py).
- Keep get_hottest_tech_discussions() and story_to_dict() importable and Hacker News only, for stock_tech_buzz_agent.py.
- Keep get_rows(), SourceError and SOURCE_NAMES importable, for the hottest discussions web app.
- Use cli_utils.py's die(), positive_int and use_utf8_output().

## Actions

- Run as python3 hottest_tech_discussions.py from the repo root.
- Take:
    - {{Sources}}: optional, repeatable, hn or lobsters (default: hn only).
    - How many discussions to return from each source (default: 10).
    - {{Tags To Exclude}}: optional, repeatable, e.g. "meta". Applies to Lobsters only, since Hacker News stories have no tags.
- Reject the options, before any network call, when a source is unknown, or when tags to exclude are given without Lobsters among the sources. Asking for the same source twice counts once.
- For Hacker News:
    - Retrieve HN's current top stories, and fetch the details of the first 4 × that many, 10 at a time.
    - Skip stories whose details fail to fetch, and anything that isn't a story (e.g. jobs).
- For Lobsters:
    - Retrieve the front pages, 25 stories a page, until there are 4 × that many candidates (at most 10 pages).
    - Stop early at an empty page.
    - Skip a story already seen on an earlier page.
    - Leave out stories carrying an excluded tag, ignoring case.
- For each source, rank its stories by score and keep the top ones.
    - Never rank stories from different sources against each other: their scores aren't comparable (Lobsters is much smaller).
    - Never combine the same story from different sources into one entry, even when both link the same article.
- Output the sources in the order hn, lobsters, whatever order they were asked for.
- Output, one section per source:
    - {{Source Name}} (Hacker News or Lobsters), as a heading.
    - One entry per discussion, ranked from 1 within its source:
        - {{Rank}} {{Title}}
        - {{Score}} {{Number of Comments}} {{Posted Time}}, in UTC
        - {{Tags}}, for Lobsters only
        - {{Article Link}} (or the discussion thread when there is none) {{Discussion Link}}
    - If a source returns no stories, say so in its section.
    - With only Hacker News, the output is the same as before Lobsters was added: no heading.
- With --json: a single array of {rank, title, score, comments, posted, url, discussion_url, tags, source}, grouped by source in the order above.
    - source is "hn" or "lobsters"; tags is [] for Hacker News.
    - rank restarts at 1 for each source.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report. The progress line names the sources being fetched.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - If any source fails, the whole run fails, with no partial output: a runtime or data failure exits with code 1, with the error on stderr, naming the source: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
