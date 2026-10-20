# Web Search (DuckDuckGo)

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the ddgs package (or the older duckduckgo_search package), which scrapes DuckDuckGo's results; no API key.
    - If neither package is installed, fail before searching.
    - Query DuckDuckGo only: pin the backend to DuckDuckGo ("duckduckgo" in ddgs, "html" in duckduckgo_search). Never use ddgs's default "auto" backend, which also scrapes Google, Yahoo, Startpage, Mojeek, Brave and Grokipedia against their robots.txt (see docs/source-audit.md).
- Use cli_utils.py's print_results() (which renders each row with format_result()).

## Actions

- Run as python3 web_search_duckduckgo.py from the repo root.
- Take:
    - {{Query}}
    - How many results to return (default: 10).
- Retrieve the results.
    - DuckDuckGo may rate-limit; report that as a failure.
- Output, one entry per result:
    - {{Rank}} {{Title}}
    - {{URL}}
    - {{Snippet}}
    - With --json: an array of {rank, title, url, snippet}, the same shape as the other web_search_*.py scripts (printed by cli_utils.print_results(), which also renders the text report through format_result()).
- If no results are returned, say so.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
