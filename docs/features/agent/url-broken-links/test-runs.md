# URL Broken Links: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/url-broken-links.md` or to `url_broken_links.py` and the `robots.py` check it uses. The agent is a prompt rather than code, so the offline pytest suite can't cover it. Its judgement is in choosing the flags from the user's wording (`https://`, `--scope`, `--max-links`, `--wayback`) and in ordering and labelling the problem links, so each case gives one fixed request chosen to exercise a rule.

These are live pages, so the counts drift; the cases judge the agent's flags and how it reports the statuses, not the exact numbers. Case 2 and 3's page is the W3C's 1992 list of web servers, kept as history, so most of its links are to hosts that are long gone.

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "url-broken-links"` and this prompt:

```text
{{Request}}

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<short-name>.out and NN-<short-name>.err (NN = the order you ran it), by redirecting, e.g. `python3 url_broken_links.py "..." --json > DIR/01-links.out 2> DIR/01-links.err; echo "exit=$?"`, then read the files.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code and the Bash timeout you set, and saying why you chose each flag. Don't end with a question.
```

Check each run against the saved `.out` / `.err` files (`checked`, `counts`, `skipped`, each link's `status`, `note`, and with `--wayback` `archived` / `archive_error`).

## Cases

Every case ran on Sonnet, the agent's model, on 2026-10-27.

### 1. A bare domain

- **Rules:** add `https://` to a bare domain; keep the default flags; if nothing is broken, say so plainly.
- **Request:** `Check example.com for broken links.`
- **A correct run:** `url_broken_links.py "https://example.com" --json` with the 600000 ms timeout and no other flags. Last time the page had no links at all (`link_count` 0), and the report said so plainly.
- **Last checked:** 2026-10-27, passed.

### 2. A page full of dead links

- **Rules:** lead with the counts; list broken and unreachable links first, then home-page redirects as likely broken, then robots-skipped links; say what was left out; mention the soft-404 limit; no `--wayback` unless asked.
- **Request:** `Are any of the links on https://www.w3.org/History/19921103-hypertext/hypertext/DataSources/WWW/Servers.html dead?`
- **A correct run:** default flags. Last time: 48 of 49 links checked (1 duplicate), 1 broken (Netcraft's survey page, 404), 31 unreachable, 5 redirected, 2 skipped for robots.txt (wdvl.internet.com, robots.txt read timed out). The report should list the 404 and the unreachable hosts, flag the Cornell link (redirects to `law.cornell.edu`'s home page, the tool's `note`) as likely broken, give the robots-skipped links as unknown, and not call them broken.
- **Last checked:** 2026-10-27, passed. It also separated a TLS certificate mismatch (`sunsite.unc.edu`) from dead hosts, and noted that the FUNET link redirects to a different site, both fair readings of `error` and `final_url`.

### 3. A cap, a scope and archived copies

- **Rules:** `--max-links N` and `--scope external` from the user's wording; `--wayback` when they want archived copies; never invent an archived copy.
- **Request:** `Check just the first 10 external links on https://www.w3.org/History/19921103-hypertext/hypertext/DataSources/WWW/Servers.html, and find archived copies of any dead ones.`
- **A correct run:** `--scope external --max-links 10 --wayback`. Last time 1 broken, 5 unreachable and 2 robots-skipped; archive.org answered the first lookup with 429, and the tool skipped the other five (`archive_error`: "not looked up: the Wayback Machine rate-limited an earlier lookup"). The report should say no archived copies were found because of the rate limit, suggest trying later, and say 30 links were over the cap and 8 out of scope.
- **Last checked:** 2026-10-27, passed.

### 4. Internal links only, with a cap

- **Rules:** `--scope internal --max-links N`; robots-skipped links given as unknown, with the URLs if there are few.
- **Request:** `Check the first 30 internal links on https://docs.python.org/3/ for broken ones.`
- **A correct run:** `--scope internal --max-links 30`. Last time 17 ok and 13 skipped because docs.python.org's robots.txt disallows the old-version paths (`/3.10/` … `/2.6/`); the report says none are broken, lists the 13 as unknown rather than broken, and gives the left-out counts (14 over the cap, 13 out of scope).
- **Last checked:** 2026-10-27, passed.

### 5. A URL that isn't a page

- **Rules:** on failure, report the error plainly; retry only a transient-looking network error.
- **Request:** `Check the links on https://www.python.org/static/img/python-logo.png for broken ones.`
- **A correct run:** one run, exit 1, `couldn't fetch the page: URL did not return HTML content (Content-Type: image/png)` reported as-is, no retry.
- **Last checked:** 2026-10-27, passed. The report said the error appeared on stdout, but the saved files show it on stderr as the convention says (`.err` 97 bytes, `.out` empty); a misreading by the agent, not a script bug.

## Not covered

- A Wayback lookup that finds a copy, including one whose archived `status` isn't 200: archive.org rate-limited the first lookup in case 3 (and in the `url-availability` spot-check on 2026-10-22).
- `blocked` links (401, 403, 429), and a page whose own site sets `ai_input_warning` or `robots_disallow_note`; no stable page found yet that triggers them.
- A page with more than 100 links, where the user then asks for the rest.
