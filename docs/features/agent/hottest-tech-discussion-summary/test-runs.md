# Hottest Tech Discussion Summary: test runs

Targeted live runs for checking the agent's edge-case rules after an edit to `.claude/agents/hottest-tech-discussion-summary.md`. The agent is a prompt rather than code, so the offline pytest suite can't cover it. Ordinary runs mostly take the easy paths, which is why each case below gives the agent one fixed topic chosen to trigger a single rule.

These are live web results. A rerun won't reproduce the earlier report exactly, and a case stops being useful once its topic no longer causes the situation, for example when a small project gets real coverage. When that happens, find a new topic that does and update the case.

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root and call the agent through the `Agent` tool with `subagent_type: "hottest-tech-discussion-summary"` and this prompt, filling in the case's row and a scratch directory:

```text
Produce your researched, sourced summary for ONE specific topic instead of the top N. Skip step 1 and use this row as the single topic:

{{Topic Row}}

Follow every other step of your workflow exactly as written, including the earlier HN threads step (2f). Apply your skip, replacement, sign-in-wall and rephrased-search rules strictly; don't bend them to avoid or to force a rephrased search.

Save the raw JSON outputs of EVERY command (search results, including any rephrased search, AND every url_content.py fetch, including failed ones) into {{Scratch Directory}} with descriptive filenames.

Return the complete final report as Markdown, to be saved verbatim. End it with a "Run notes" section saying explicitly: (a) every result replaced from the spares and why; (b) for each engine, whether the rephrased-search trigger fired, what the rephrased query was, and what it returned, or why it didn't fire; (c) any page you treated as mostly a sign-in wall. Don't end with a question.
```

Save the report as `tmp/hottest-discussions-<date>[-n].md` (git-ignored), choosing a suffix that doesn't overwrite an earlier report. Don't judge the run from its run notes alone: check its skip, replacement and trigger decisions against the raw JSON in the scratch directory.

## Cases

### 1. Rephrased search when the skips leave nothing to fetch

- **Rule:** step 2d's "one rephrased search per engine" (commits `d71c52b`, `678db36`).
- **Topic:** Show HN "OneDeploy". Its name collides with onedeploy.com (an unrelated Windows deployment product), Azure's `onedeploy` API and OpenNebula's one-deploy, so the first searches return only its own links, social sites and other OneDeploys.
- **Row:**
  ```json
  {"rank": 1, "title": "Show HN: OneDeploy – Managed open-source apps with nightly backups and TLS", "score": 28, "comments": 11, "posted": "2026-10-16 15:38 UTC", "url": "https://onedeploy.co", "discussion_url": "https://news.ycombinator.com/item?id=50119752"}
  ```
- **A correct run:**
  - Every first-search result from both engines is skipped in 2c: own links, Reddit/YouTube, or a different subject.
  - The rephrased search fires once per engine, with the subject's own name plus what it is (last time `onedeploy.co open-source apps`).
  - The same 2c skips are applied to the new results, and the agent then stops: no second rephrased search and no third engine.
  - The report says plainly how few sources it found. Last time that was one, `onedeploy.co/terms`, from Serper.
- **Last checked:** 2026-10-19, passed.

### 2. Name collision that shouldn't trigger anything

- **Rule:** the different-subject skip in 2c and the rephrased-search trigger, from the "don't fire" side.
- **Topic:** Show HN "Sphinx", which shares its name with the Python documentation tool. Its trending day brought enough write-ups that each engine had real content.
- **Row:**
  ```json
  {"rank": 21, "title": "Show HN: Sphinx – A hook that quizzes you on your AI's code before shipping", "score": 243, "comments": 85, "posted": "2026-10-18 04:33 UTC", "url": "https://sphinx-six-theta.vercel.app/", "discussion_url": "https://news.ycombinator.com/item?id=50137950"}
  ```
- **A correct run:**
  - No result about the Python Sphinx tool is kept. If none come back, none are skipped as a different subject.
  - Each engine keeps at least one result with real content, so no rephrased search runs.
  - Social and video results (Instagram, YouTube) are skipped, and a result already collected from the first engine is skipped as a duplicate.
- **Last checked:** 2026-10-19, passed.

### 3. Replacing a dropped result from the spares

- **Rule:** step 2d's "replace a dropped result once, from the spares" (commit `eea3252`).
- **Topic:** "RepRapMicron". Last time, two search results (Printables and 3druck) refused the fetch with HTTP 403.
- **Row:**
  ```json
  {"rank": 1, "title": "RepRapMicron", "score": 345, "comments": 55, "posted": "2026-10-18 13:48 UTC", "url": "https://github.com/VikOlliver/RepRapMicron/wiki", "discussion_url": "https://news.ycombinator.com/item?id=50141076"}
  ```
- **A correct run:**
  - A failed, near-empty or pointer result is replaced by that engine's next unskipped spare.
  - The dropped result stays in the link list, marked as dropped, with its replacement listed after it.
  - When an engine has no unskipped spares left, the agent carries on with fewer results and says so, instead of borrowing from another engine.
- **Caveat:** this case depends on sites that block the fetch today. If every result fetches cleanly, the run proves nothing about this rule; note that rather than counting it as a pass.
- **Last checked:** 2026-10-19 (during an ordinary top-3 run), passed.

### 4. A page that is mostly a sign-in wall

- **Rule:** step 2d's "a page that is mostly a sign-in wall counts as dropped too" (commit `6c4d704`).
- **Topic:** none yet. The case needs a topic whose searches return a page that is mostly a login prompt with a few headlines or teasers around it, such as a LinkedIn profile or a Medium author page. A full LinkedIn post that comes through around the sign-in links is real content and doesn't count; that is what happened in the "Someone behind the software" run.
- **A correct run:** the walled page is marked as dropped, not "used, partially", and is replaced from the engine's spares.
- **Last checked:** never run.

### 5. Lobsters topics and a story shared with Hacker News

- **Rules:** step 1b's "combine stories shared between sources", step 2a's per-site thread script, and Step 3's source tags (commit `3ec9b51`).
- **Topics:** three rows, as if step 1 had run with `--source hn --source lobsters`. HN's "Claude reveals ECDSA curve origins" and Lobsters' "The NIST Elliptic Curves Seeds Bounty Has Been Claimed" are the same story under different links. Lobsters' ARP post is unrelated and must stay its own topic.
- **Prompt:** this case gives several rows, so replace the template's first paragraph with: "Produce your researched, sourced summary for these specific rows instead of the top N. Skip step 1 and use these rows as its output, as if both sources had been asked for:", followed by the rows as one JSON array. Add "(d) which rows you combined and why" to the run notes.
- **Rows:**
  ```json
  [
    {"rank": 1, "title": "Claude reveals ECDSA curve origins", "score": 1051, "comments": 388, "posted": "2026-10-16 18:55 UTC", "url": "https://www.anthropic.com/research/ecdsa-curve-origins", "discussion_url": "https://news.ycombinator.com/item?id=50122800", "tags": [], "source": "hn"},
    {"rank": 1, "title": "The NIST Elliptic Curves Seeds Bounty Has Been Claimed", "score": 135, "comments": 38, "posted": "2026-10-16 20:18 UTC", "url": "https://words.filippo.io/seeds-solved/", "discussion_url": "https://lobste.rs/s/ddtqtn/nist_elliptic_curves_seeds_bounty_has", "tags": ["cryptography", "vibecoding"], "source": "lobsters"},
    {"rank": 2, "title": "ARP! Tell your network to explain itself", "score": 36, "comments": 13, "posted": "2026-10-18 12:48 UTC", "url": "https://benjcal.space/blog/arp-tell-your-network-to-explain-itself/", "discussion_url": "https://lobste.rs/s/mmvhup/arp_tell_your_network_explain_itself", "tags": ["networking"], "source": "lobsters"}
  ]
  ```
- **A correct run:**
  - Two topics, not three: the ECDSA story combined, tagged `[HN] [Lobsters]`, at the HN position; the ARP post on its own, tagged `[Lobsters]`. The report says one story was combined.
  - The HN thread is read with `hn_thread.py` and both Lobsters threads with `lobsters_thread.py`; no thread is fetched with `url_content.py`.
  - Both of the combined topic's articles are fetched, and its discussion summary keeps HN's and Lobsters' commenters apart, without comparing the two sites' scores.
  - The combined topic's web search skips both articles and both threads as own links.
  - Lobsters' topic tags (`cryptography`, `networking`) appear only on the Lobsters lines, never inside the source-tag brackets.
- **Last checked:** 2026-10-19, passed.
