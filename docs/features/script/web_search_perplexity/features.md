# Web Answer (Perplexity)

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Perplexity Sonar API.
- Read PERPLEXITY_API_KEY from the environment, or from a .env file at the repo root via cli_utils.load_dotenv() (a real environment variable wins).
    - If the key is missing, fail before making any request.
- Use cli_utils.py's load_dotenv().

## Actions

- Run as python3 web_search_perplexity.py from the repo root.
- Take:
    - {{Query}}: a question or search query.
    - The Sonar model (default: sonar), e.g. sonar-pro, sonar-reasoning, sonar-reasoning-pro.
    - How many sources to show (default: 10). Perplexity decides how many to cite; this only trims the list.
- Ask the model; it searches the web itself and writes an answer.
    - A response with no answer, or an empty one, is a failure.
- Output:
    - {{Answer}}
    - One entry per source: {{Rank}} {{Title}} {{URL}} {{Date}}
    - With --json: {answer, sources: [{rank, title, url, date}]}.
- The output is an answer plus sources, not a flat list of results, so this script is not part of the web-search agent's fallback chain.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
