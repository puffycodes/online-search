# Web Search (DuckDuckGo)

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the ddgs package (or the older duckduckgo_search package), which scrapes DuckDuckGo's results; no API key.
    - If neither package is installed, fail before searching.
- Use cli_utils.py's format_result() and print_results().

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
    - With --json: an array of {rank, title, url, snippet}, the same shape as the other web_search_*.py scripts (via cli_utils.format_result()).
- If no results are returned, say so.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
