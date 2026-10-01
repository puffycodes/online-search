# Stock Tech Buzz

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use market_top_volume.py's get_movers() and hottest_tech_discussions.py's get_hottest_tech_discussions(), imported directly (not run as separate processes).

## Actions

- Run as python3 stock_tech_buzz_agent.py from the repo root.
- Take:
    - How many top-volume stocks to pull per exchange (default: 10).
    - How many hottest tech discussions to search (default: 50).
- Retrieve the top-volume stocks on NYSE and on Nasdaq, removing duplicates.
- Retrieve the hottest tech discussions on Hacker News.
- Match each stock against each discussion title:
    - The ticker as a whole word, case-sensitive (e.g. NVDA), unless it's a common word such as AI, ON or IT.
    - Or the company name, with suffixes like "Inc." and "Corporation" removed, as a whole word or phrase, case-insensitive.
- Keep only the stocks mentioned in at least one discussion.
- Output, one entry per mentioned stock:
    - {{Symbol}} {{Company Name}} {{Exchange}} {{Volume}} {{Price}} {{Percent Change}}
    - Each matching discussion: {{Title}} {{Score}} {{Number of Comments}} {{Discussion Link}}
    - With --json: an array of {symbol, name, exchange, volume, price, change_percent, discussions: [{title, score, comments, discussion_url}]}.
- If no stock is mentioned, say so.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
