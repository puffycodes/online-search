# Web Search (SerpApi)

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the SerpApi API with its Google engine.
- Read SERPAPI_API_KEY from the environment, or from a .env file at the repo root via cli_utils.load_dotenv() (a real environment variable wins).
    - If the key is missing, fail before making any request.
- Use cli_utils.py's load_dotenv(), format_result() and print_results().

## Actions

- Run as python3 web_search_serpapi.py from the repo root.
- Take:
    - {{Query}}
    - How many results to return (default: 10).
- Retrieve the results, up to 100 per request, paging for more.
- Treat an error field in the response body (e.g. an invalid key or quota used up) as a failure.
    - Except a "hasn't returned any results" message in that field, which means no (more) results, not a failure. (A query with no results normally just returns an empty list.)
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
