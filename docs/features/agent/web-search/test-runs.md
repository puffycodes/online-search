# Web Search: test runs

Targeted live runs for checking the agent's fallback rules after an edit to `.claude/agents/web-search.md` or to the six `web_search_*.py` scripts it chains. The agent is a prompt rather than code, so the offline pytest suite can't cover it, and an ordinary search always takes the easy path (Brave answers first time). Each case below forces one failure with an environment variable set on the command line, so neither `.env` nor the agent file needs editing:

- `BRAVE_API_KEY=` (empty) — a missing key. `cli_utils.load_dotenv()` never overrides a variable that is already set, so the script sees no key and `require_env()` refuses.
- `BRAVE_API_KEY=invalid-test-key` — a wrong key, which Brave rejects with `HTTP 422: SUBSCRIPTION_TOKEN_INVALID`.
- `HTTPS_PROXY=http://127.0.0.1:9` (and `HTTP_PROXY` for DuckDuckGo) — a network failure: nothing listens on port 9, so every request fails at once with a refused connection.

These are live searches. The results change over time; the cases judge the agent's choices (which scripts it ran, retries, fallbacks, what it reported), not the result lists.

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "web-search"` and this prompt:

```text
Search the web for: RFC 9309 robots exclusion protocol. Give me the top 5 results.

This is a targeted test run of your fallback rules. {{Case Instruction}} Change nothing else in your workflow.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<engine>.out and NN-<engine>.err (NN = the order you ran it, 01, 02, ...), by redirecting, e.g. `{{Prefix}}python3 web_search_brave.py "..." --json > DIR/01-brave.out 2> DIR/01-brave.err; echo "exit=$?"`, then read the files.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code and a one-line summary of its stderr, and saying why you did or didn't retry or fall back. Don't end with a question.
```

The cases are independent and can run in parallel. Don't judge a run from its run notes alone: check the numbered files in the scratch directory (which scripts ran, in what order, their exit codes and stderr) against the pass criteria. Scan the `.err` files for API keys before keeping or sharing them (see case 5).

## Cases

### 1. Normal path

- **Rule:** "Never run more than one script when the first one already returned results"; pass `--limit` only when the user asked for a count; don't name the engine when it's Brave.
- **Case instruction:** "Follow it exactly as written; change nothing." (no prefix)
- **A correct run:**
  - One command: `web_search_brave.py ... --limit 5 --json`, exit 0, empty stderr, five results.
  - No other script runs; the report doesn't mention which engine answered.
- **Last checked:** 2026-10-21, passed.

### 2. Missing key

- **Rule:** fall back on a missing key; don't retry it.
- **Case instruction:** "Prefix every command you run with `BRAVE_API_KEY= ` (an empty value)."
- **A correct run:**
  - `01-brave` exits 1 with `BRAVE_API_KEY environment variable must be set`; it is not run again.
  - `02-serper` exits 0, and the agent stops there.
  - The report says the results came from Serper because Brave's key was missing.
- **Last checked:** 2026-10-21, passed.

### 3. Invalid key

- **Rule:** "If a script's error output complains about an invalid or unauthorized key, fall through to the next script as usual, but flag the specific key as possibly misconfigured."
- **Case instruction:** "Prefix every command you run with `BRAVE_API_KEY=invalid-test-key `."
- **A correct run:**
  - `01-brave` exits 1 with `HTTP 422: SUBSCRIPTION_TOKEN_INVALID: The provided subscription token is invalid.`; it is not retried.
  - `02-serper` answers and the agent stops.
  - The report names `BRAVE_API_KEY` as possibly misconfigured.
- **Found on 2026-10-21:** Brave's stderr was only `422 Client Error:  for url: …`, because the scripts called `response.raise_for_status()`, which drops the API's own message. The agent still flagged the key, but by guesswork. Fixed the same day: the keyed `web_search_*.py` scripts now go through `cli_utils.raise_for_status()`, which keeps the provider's reason.
- **Last checked:** 2026-10-21, passed (the agent run predates the fix; the fixed stderr was checked by running the script directly).

### 4. Transient error

- **Rule:** "Retry a given script at most once, and only for a transient-looking network error."
- **Case instruction:** "Prefix every `web_search_brave.py` command you run with `HTTPS_PROXY=http://127.0.0.1:9 `; run every other script without it."
- **A correct run:**
  - `01-brave` and `02-brave` both exit 1 with a refused-connection `ProxyError`: exactly one retry.
  - `03-serper` answers and the agent stops.
  - The report says Brave couldn't be reached and the results came from Serper.
- **Last checked:** 2026-10-21, passed.

### 5. Every engine fails

- **Rule:** the chain's end: "If DuckDuckGo also fails, stop and report the error", "tell the user plainly that no web search is currently available", and never substitute `web_search_perplexity.py`.
- **Case instruction:** "Prefix every command you run with `HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 `."
- **A correct run:**
  - Twelve commands: Brave, Serper, Tavily, SerpApi, Exa, DuckDuckGo, in that order, each run twice (one retry for a network error), all exit 1.
  - No `web_search_perplexity.py`, no results from the agent's own knowledge.
  - The report says plainly that no web search is available and why.
- **Found on 2026-10-21:** `web_search_serpapi.py` sends its key as a URL query parameter, and a connection error's message contains the URL, so the key was printed in the error and saved in `07-serpapi.err` and `08-serpapi.err`. Fixed the same day: the keyed scripts pass their error messages through `cli_utils.redact()`, and the two files were redacted. The run was otherwise correct.
- **Last checked:** 2026-10-21, passed.

## Not covered

- **A quota or rate-limit message** ("don't retry an unambiguous rate-limit/quota message") can't be produced on demand without using up a real quota. With `cli_utils.raise_for_status()` the provider's wording (e.g. Brave's `RATE_LIMITED`) now reaches the agent, so check the run notes the next time a quota does run out.
- **An empty result list** ("say so plainly instead of inventing content") needs a query no engine matches, which is hard to keep stable.
