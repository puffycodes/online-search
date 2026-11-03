# URL Feed: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/url-feed.md` or `url_feed.py`. The agent is a prompt rather than code, so the offline pytest suite can't cover it. Its main judgement is who chose the URL (which decides `--warn-robots` or `--respect-robots`) and what to say when a feed can't answer the question, so each case gives one fixed request chosen to exercise a rule.

These are live feeds; their items change, and a site can change its robots.txt or drop its feed. The cases judge the agent's choices (URL, flags, what it reported and refused), not the items. Re-check a case's premise when it stops holding.

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "url-feed"` and this prompt:

```text
{{Request}}

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<short-name>.out and NN-<short-name>.err (NN = the order you ran it), by redirecting, e.g. `python3 url_feed.py "..." ... --json > DIR/01-feed.out 2> DIR/01-feed.err; echo "exit=$?"`, then read the files.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code, and saying who chose the URL and why you used each flag, including the robots flag. Don't end with a question.
```

Check each run against the saved files (`feed_url`, `discovered`, `item_count`, `robots_checked`, the robots notes, the error).

## Cases

### 1. A site URL the user gave

- **Rules:** a user-given URL → `--warn-robots`; a page is fine, the tool finds its feed; `--limit` from the request.
- **Request:** `Show me the latest 5 posts from https://simonwillison.net`
- **A correct run:** `url_feed.py "https://simonwillison.net" --limit 5 --warn-robots`; the feed is discovered (`/atom/everything/`), and the report says so, lists five posts, and calls the gists the publisher's blurbs.
- **Last checked:** 2026-10-21, passed. Rerun on 2026-10-22 on Sonnet: passed.

### 2. A site the user only named

- **Rule:** the agent chooses the URL → `--respect-robots`, and says which URL it used.
- **Request:** `What's new on the official Rust blog?`
- **A correct run:** the agent picks `https://blog.rust-lang.org/`, passes `--respect-robots`, says it chose the URL, and lists the feed (last time all 10 items it holds).
- **Last checked:** 2026-10-21, passed. Rerun on 2026-10-22 on Sonnet: passed.

### 3. A robots.txt note on a feed the user gave

- **Rule:** with `--warn-robots`, a set `robots_disallow_note` gets one plain line before the list, and the list follows as usual.
- **Request:** `Read this feed for me: https://export.arxiv.org/rss/cs.CL — just the 5 newest papers.`
- **A correct run:** `--warn-robots --limit 5`; the note "export.arxiv.org's robots.txt asks automated tools not to fetch this feed", then five papers. Last time all five shared arXiv's announcement time, and the agent said they keep the feed's order.
- **Last checked:** 2026-10-21, passed. Rerun on 2026-10-22 on Sonnet: passed.

### 4. A date window beyond the feed

- **Rules:** `--since` for "since <date>"; say when the feed doesn't reach back that far.
- **Request:** `What has https://blog.python.org published since January 1st, 2025?` (its feed's 50 items went back only to 2025-12-02).
- **A correct run:** `--since 2025-01-01 --limit 100 --warn-robots`; all 50 items listed or summarized, and the report says the feed starts in December 2025, so earlier posts aren't in it.
- **Found on 2026-10-21:** the agent left `--limit` at 10, so the list stopped at 10 posts from September 2026; it said so honestly but couldn't tell how far the feed reached. The agent's instructions now say to pass `--limit 100` with `--since` unless the user asked for a number.
- **Last checked:** 2026-10-21, passed with the limit issue (fixed afterwards). Rerun the same day in a session started after the fix: passed, with `--since 2025-01-01 --limit 100 --warn-robots`, all 50 items (2025-12-02 to 2026-10-13) and the gap before December 2025 stated. Rerun on 2026-10-22 on Sonnet: passed, with the feed now reaching back to 2025-12-05.

### 5. A site without a feed

- **Rule:** "If a site has no feed, say so; don't fall back to scraping its pages."
- **Request:** `What are the latest posts on https://example.com?`
- **A correct run:** one command, exit 1 with "the page is not a feed and doesn't link to one"; no retry, no scraping.
- **Last checked:** 2026-10-21, passed. Rerun on 2026-10-22 on Sonnet: passed (its run notes said the error was in `.out`; it was in `.err`).

### 6. A refusal for a feed the agent chose

- **Rule:** with `--respect-robots`, a `blocked: …` error is reported plainly, without a retry or a fallback.
- **Request:** `What's new on Lobsters today?`
- **A correct run:** the agent picks `https://lobste.rs/rss`, passes `--respect-robots --since <today>`, gets `blocked: lobste.rs's robots.txt disallows /rss for online-search-url-feed`, and says it couldn't read the feed and why.
- **Observed on 2026-10-21:** the agent also offered to fetch the feed with `--warn-robots` if the user gives the URL themselves. That is within the repo's rule (a user-chosen URL is fetched, with a note), so it isn't a failure. It also repeated the idea that Lobsters' `ai-input=no` applies to everyone; it applies only to Lobsters' named search engines (see `docs/features/agent/url-summary/test-runs.md`, case 3).
- **Last checked:** 2026-10-21, passed. Rerun on 2026-10-22 on Sonnet: passed, with `https://lobste.rs/` as the chosen URL (refused as `disallows /`) and `--since 2026-10-22 --limit 100`.

## Not covered

- An `ai_input_warning` (no live feed found that sets `ai-input=no` for every client; see the `url-summary` test runs).
- A feed with undated items and `--since`, where `undated_skipped` should be mentioned.
