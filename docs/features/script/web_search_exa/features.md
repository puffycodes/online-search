# Web Search (Exa)

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Exa Search API (semantic search).
- Read EXA_API_KEY from the environment, or from a .env file at the repo root via cli_utils.load_dotenv() (a real environment variable wins).
    - If the key is missing, fail before making any request.
- Use cli_utils.py's load_dotenv(), require_env() and print_results() (which renders each row with format_result()).

## Actions

- Run as python3 web_search_exa.py from the repo root.
- Take:
    - {{Query}}
    - How many results to return (default: 10). Exa has no paging, so a larger number is capped at 100 rather than rejected.
- Retrieve the results in one request.
- Use each result's page text, cut to 300 characters by Exa, as the snippet.
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
- On an HTTP error, report the provider's own reason when it gives one (cli_utils.raise_for_status()), and never show the API key: replace it with <redacted> in any error message (cli_utils.redact()).
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
