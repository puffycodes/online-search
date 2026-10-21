# HN Search: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/hn-search.md`, `hn_search.py` or `hn_thread.py`. The agent is a prompt rather than code, so the offline pytest suite can't cover it, and its hardest choices (which searches to run, which comments to set aside, how to frame a sample) only show up in live runs. Each case below gives the agent one fixed question chosen to exercise a rule.

These are live searches over a growing archive. Counts and comments change, so the cases judge the agent's choices (tools, queries, flags, what it set aside and how it framed the result), not its findings. Re-check a case's premise when it stops holding (for example, if a name stops being ambiguous).

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "hn-search"` and this prompt:

```text
{{Question}}

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<short-name>.out and NN-<short-name>.err (NN = the order you ran it, 01, 02, ...), by redirecting, e.g. `python3 hn_search.py "..." ... --json > DIR/01-stories.out 2> DIR/01-stories.err; echo "exit=$?"`, then read the files.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code, and for each saying why you chose that query, those flags and that tool. Also say how many comments the summary is based on and how many you set aside as off-topic, and why. Don't end with a question.
```

The cases are independent and can run in parallel; the opinion cases take about two minutes each. Check each run against the saved files (queries, `type`, `sort`, `since` / `until`, `total_matches`, `job_threads_skipped`, `shown_comments`) and spot-check that quoted comments exist with the words attributed to them.

## Cases

### 1. Opinions on a distinctive name

- **Rules:** "For 'what does HN think of X?', a good chain is: a story search to find the biggest thread(s), then `hn_thread.py` on the top one or two, plus a comment search for recent views"; distinctive names need no context word; "a sample, not a poll".
- **Question:** `What does HN think of Zig?`
- **A correct run:**
  - A story search for `"zig"`, then `hn_thread.py` on one or two threads that are about Zig itself (not just mentioning it), then a date-sorted comment search with no context word.
  - Says how many comments it read and set aside, and that this is a sample. Attributes the top comment's tone with the usual caveat.
- **Found on 2026-10-21:** the agent noticed that the top-scoring "Zig Creator Calls Spade a Spade" story links to a "zed-creator" post and didn't treat it as a Zig thread. A good catch, and the reason to read before using a result.
- **Last checked:** 2026-10-21, passed.

### 2. An ambiguous name

- **Rules:** "Keeping comment searches on topic": search inside the topic's own threads first; if a context word is used, run two with different words and weight views found in both; never present the context word's topic as a finding; report how many comments were set aside.
- **Question:** `What does Hacker News think of Swift, the programming language, these days?`
- **A correct run:**
  - Story search, then `hn_thread.py` on Swift-language threads (e.g. a release thread, a notable adoption or abandonment).
  - Two comment searches with different context words (last time `"swift xcode"` and `"swift language"`), date-sorted over recent months, avoiding `"swift apple"` and skill-list words.
  - Explicitly declines to count the context word's subject (Xcode complaints) as a finding, and lists what was set aside (off-topic stories such as "Swift bricks" for birds, comments that only list Swift).
- **Last checked:** 2026-10-21, passed.

### 3. Hiring demand

- **Rules:** `--include-job-threads` only for jobs and hiring questions; counts of matching comments aren't counts of jobs.
- **Question:** `Is Rust in demand in HN's hiring threads this year?`
- **A correct run:**
  - Finds the year's "Who is hiring?" threads (`--author whoishiring --type ask --include-job-threads`) and searches inside each with `"rust" --story ITEM --include-job-threads`.
  - Compares with one or two other skills, reports per-month counts, and says what they are and aren't (posts mentioning the word, replies mixed in).
- **Found on 2026-10-21:** the agent's first step, a site-wide `"rust" --type comment --include-job-threads` search, returned only general Rust discussion. It recovered by finding the threads first. That method is now written into the agent's instructions.
- **Last checked:** 2026-10-21, passed (after the agent's own recovery). Rerun the same day in a session started after the fix: passed. The agent went straight to the ten 2026 threads, searched `"rust"`, `"python"` and `"typescript"` inside each (totals 264 / 779 / 713, matching the saved files), read the Rust matches and set aside 7 replies. One slip in its caveats: it said it read 244 Rust comments with 20 unread, but at `--limit 30` it read 253 and left 11 (February and April) unread.

### 4. Summarizing a linked thread

- **Rules:** "Reading a thread": `hn_thread.py` on the link; lead with title, score and comment count; say how many of `total_comments` were read; the top comment sets the tone without being a majority view.
- **Question:** `Summarize the comments on https://news.ycombinator.com/item?id=41002195` (the CrowdStrike outage thread: 4,489 points, about 3,800 comments).
- **A correct run:**
  - One `hn_thread.py` call on the link, no search needed.
  - Reports "71 of 3,767" (or whatever `shown_comments` / `total_comments` say), groups views, links the comments it draws on, and notes how much sits under the comments shown (`total_replies`).
- **Last checked:** 2026-10-21, passed (five quoted comments spot-checked against the saved JSON).

### 5. "Lately"

- **Rules:** `--sort date` for "lately"; `--min-points` with date-sorted stories to skip noise; a context word for an everyday name, with the same two-word discipline as case 2.
- **Question:** `What has HN been saying about Bun lately?`
- **A correct run:**
  - A date-sorted story search with a recent `--since` and a points floor, then `hn_thread.py` on the latest big threads, then two date-sorted comment searches with different context words (last time `"bun node"` and `"bun runtime"`).
  - Notes when the context words shaped the sample (last time, both pulled comments from the Deno / Cloudflare threads).
- **Last checked:** 2026-10-21, passed.

### 6. Nothing matches

- **Rule:** "If `results` is empty, say nothing matched, and suggest (or run) a broader query"; never fabricate.
- **Question:** `Find HN threads about the Frobnitzky protocol.`
- **A correct run:**
  - The search returns 0; the agent broadens once or twice (drops a word, tries comments), all 0.
  - Says plainly that nothing matched, without inventing threads or guessing at other names.
- **Last checked:** 2026-10-21, passed.

### 7. One topic inside a big thread

- **Rule:** "To follow one topic inside a big thread, run `hn_search.py "TOPIC" --story ITEM` on it."
- **Question:** `In the big HN thread about the CrowdStrike outage (https://news.ycombinator.com/item?id=41002195), what did people say about Microsoft?`
- **A correct run:**
  - `hn_search.py "microsoft" --story 41002195`, with enough results to allow skips, and comments sampled from more than one period of the thread.
  - Groups the views, reports how many comments were used and set aside, and says which part of the thread the sample covers.
- **Found on 2026-10-21:** a `--story` search by relevance came back newest first (July 20–23), because comments have no score and relevance ties on the word. The agent noticed and added a second search with `--until 2024-07-19` for day one. A direct check showed the same for site-wide comment searches (`"zig"` and `"kubernetes"` by relevance returned only 2015 comments). The agent's instructions now say to pick the period with `--sort date` and `--since` / `--until` for comment searches and to sample a long thread in more than one window; the README's `hn_search.py` notes say so too.
- **Last checked:** 2026-10-21, passed. Rerun the same day in a session started after the fix: passed. The agent searched by date in two windows (day one, then 20 July on) and read the thread's top-ranked comments, and said which part of the thread each covered.
- **Found on the rerun:** `--since` / `--until` work in whole days, so a date-sorted search of day one (152 matches) only reached its last hours (16:30–23:59 UTC); the thread's first eleven hours were out of reach. The agent said so and used `hn_thread.py`'s top-ranked comments, which skew early, to cover them.

### 8. One author's comments

- **Rules:** `--author` with `--type comment` for what one user has said; `--sort date` with `--since` / `--until` windows for comments; "a sample, not a poll".
- **Question:** `What has pg commented about startups?`
- **A correct run:**
  - `hn_search.py "startups" --type comment --author pg --sort date` over several date windows (last time five, 2008 to 2014), no story search or `hn_thread.py`.
  - Groups views by theme, links each quoted comment, gives how many comments were used and set aside, and says it's one person's comments, not a full index of his views.
- **Found on 2026-10-21:** 44 of the comments returned for `"startups"` (complete texts, not cut) contain only "startup", and the story title doesn't have the plural either. Algolia matches singular and plural forms despite whole-word matching, so `total_matches` (1,548) counts both. The README's `hn_search.py` notes say a plural "may need its own search"; for English plurals it doesn't.
- **Last checked:** 2026-10-21, passed (six quotes spot-checked against the saved JSON).

## Not covered

- **Invalid arguments** (exit 2: fix rather than retry), e.g. `--min-points` with `--type comment`. No natural question triggers them; check the run notes when one turns up. Seen once, in the case 7 rerun on 2026-10-21: `hn_thread.py --top 0` exited 2, and the agent fixed the argument (`--top 30`) rather than retrying it.
