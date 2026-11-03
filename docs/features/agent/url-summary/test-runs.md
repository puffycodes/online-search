# URL Summary: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/url-summary.md` or to `url_content.py`. The agent is a prompt rather than code, so the offline pytest suite can't cover it, and an ordinary request (one well-formed URL to a normal page) takes the easy path. Each case below gives the agent one fixed input chosen to trigger a single rule.

These are live pages. They can change (a page gains a title, a site edits its robots.txt), so a rerun won't reproduce the earlier summary, and a case stops being useful once its page no longer causes the situation. When that happens, find a new page that does and update the case. The cases judge the agent's choices (commands, retries, labels, notes, what's reported for failures, whether a combined take is written), not the summaries' wording.

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "url-summary"` and this prompt:

```text
{{Request}}

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<short-name>.out and NN-<short-name>.err (NN = the order you ran it, 01, 02, ...), by redirecting, e.g. `python3 url_content.py "..." ... > DIR/01-page.out 2> DIR/01-page.err; echo "exit=$?"`, then read the files.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code and a one-line summary of its stderr, saying why you did or didn't retry, and (for several URLs) whether you wrote a combined take across the pages and why. Don't end with a question.
```

The cases are independent and can run in parallel. Check each run against the saved `.out` / `.err` files (`title`, `truncated`, `ai_input_warning`, `robots_disallow_note`, the errors), not just its run notes.

## Cases

### 1. Bare domain, long page

- **Rules:** "if the user gave a bare domain or path, add `https://` yourself"; mention `truncated` and offer a higher `--max-chars`.
- **Request:** `Summarize this page: en.wikipedia.org/wiki/Link_rot`
- **A correct run:**
  - One command: `url_content.py "https://en.wikipedia.org/wiki/Link_rot" --text --max-chars 6000 --warn-robots --json`, exit 0.
  - Labelled **Link rot - Wikipedia** with the URL; no robots note.
  - Says the page was cut off (6,000 of about 17,760 characters) and offers a re-fetch with a higher `--max-chars`.
- **Last checked:** 2026-10-21, passed. Rerun on 2026-10-22 on Sonnet: passed.

### 2. A page without a title

- **Rule:** "When `title` is `null`, label it with the URL alone; don't make up a title from the content."
- **Request:** `Summarize this page: https://www.rfc-editor.org/rfc/rfc9309.txt` (plain text, so `title` is `null`).
- **A correct run:**
  - The summary is labelled with the URL only, even though the text plainly says "Robots Exclusion Protocol".
  - Truncation is mentioned (6,000 of 20,410 characters).
- **Last checked:** 2026-10-21, passed. Rerun on 2026-10-22 on Sonnet: passed (labelled with the URL, though the report called that "my own label").

### 3. A page whose robots.txt asks automated clients not to fetch it

- **Rule:** the `robots_disallow_note` line under the label, then the summary as usual ("Don't skip or shorten its summary because of the note, and don't lecture").
- **Request:** `Summarize this page: https://lobste.rs/about`. Lobsters' robots.txt ends with `User-agent: *` / `Disallow: /`.
- **A correct run:**
  - The JSON has `robots_disallow_note` set and `ai_input_warning` `null`.
  - The report has exactly one line under the label, "Note: lobste.rs's robots.txt asks automated tools not to fetch this page.", followed by a full summary.
- **About `ai_input_warning` being `null`:** Lobsters' `Content-Signal: ai-input=no, ai-train=no, search=yes` line sits in the group for its named search engines (Applebot, BingBot, GoogleBot, …). A blank line doesn't end a group (RFC 9309), so `robots.py` applies it to those crawlers only. That is the reading recorded in CLAUDE.md, not a bug.
- **Last checked:** 2026-10-21, passed. Rerun on 2026-10-22 on Sonnet: passed.

### 4. Failures in a list of URLs

- **Rules:** retry only a transient-looking network error; "Always account for every URL the user gave, even ones whose content couldn't be fetched", in the order given; no synthesis forced across pages.
- **Request:** `Summarize these three pages for me: https://example.com, https://example.com/no-such-page-xyz, https://www.rfc-editor.org/rfc/rfc9309.pdf`
- **A correct run:**
  - Three commands, one per URL, none retried: `example.com` exits 0, the second exits 1 with `404 Client Error: Not Found`, the PDF exits 1 with `URL did not return text content (Content-Type: application/pdf)`.
  - The report lists all three in the order given: a summary for **Example Domain**, then each failure with its reason, saying there's nothing to summarize.
  - No combined take (only one page had content).
- **Last checked:** 2026-10-21, passed. Rerun on 2026-10-22 on Sonnet: passed.

### 5. Related pages: a combined take

- **Rule:** "Only add a short combined take connecting the pages if a real relationship actually exists between them."
- **Request:** `Summarize these two pages: https://www.rfc-editor.org/info/rfc9309/ and https://en.wikipedia.org/wiki/Robots.txt`
- **A correct run:**
  - Each page summarized separately under its title, in order, each noting its truncation.
  - A short combined take saying how they relate (the RFC is the specification; the article gives history and context and cites the RFC).
- **Last checked:** 2026-10-21, passed. Rerun on 2026-10-22 on Sonnet: passed.

### 6. Unrelated pages: no combined take

- **Rule:** "don't force a synthesis across unrelated pages just because there's more than one."
- **Request:** `Summarize these two pages: https://en.wikipedia.org/wiki/Link_rot and https://www.python.org/about/`
- **A correct run:**
  - Two separate summaries in order, with no combined take.
  - The run notes say why: the pages share no topic.
- **Last checked:** 2026-10-21, passed. Rerun on 2026-10-22 on Sonnet: passed.

## Not covered

- **`ai_input_warning`**, the stronger note ("asks AI tools not to use its content"), and the wording for both notes at once. They need a page whose site applies `Content-Signal: ai-input=no` to every client. None was found on 2026-10-21 among a dozen large sites (Cloudflare, The Verge, Medium, Reddit, Stack Overflow, NYT, BBC, Ars Technica, Wired) and several pages that write about Content-Signal. Add a case when one turns up.
- **A transient network error** (one retry, then report the failure). It could be forced with `HTTPS_PROXY=http://127.0.0.1:9`, as in `docs/features/agent/web-search/test-runs.md`, if that rule changes.
