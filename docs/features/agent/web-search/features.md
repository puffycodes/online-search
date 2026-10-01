# Web Search

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the web_search_*.py scripts (Brave, Serper, Tavily, SerpApi, Exa, DuckDuckGo) to retrieve the search results.

## Actions

- Take a search query given by the user.
- Take how many results to return.
    - The default is 10.
- Search with one engine, in this order of preference, moving to the next only when one fails (missing key, quota used up, error):
    - Brave → Serper → Tavily → SerpApi → Exa → DuckDuckGo
    - Stop at the first engine that returns results.
    - Retry an engine at most once, only for a transient network error.
    - Do not use web_search_perplexity.py; it returns an answer, not a list of results.
- Output a numbered list, one result per entry:
    - {{Title}}
    - {{URL}}
    - {{Snippet}}, one or two lines.
- Say which engine produced the results if it wasn't Brave, and note that Exa ranks results by meaning rather than keywords.
- If an engine's key looks invalid (not just missing), say so.
- If every engine fails, say that no web search is available, and why.
- If no results are returned, say so plainly.
- Never fabricate results, titles or URLs.
