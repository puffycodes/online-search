# Package Vulnerabilities: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/package-vulnerabilities.md` or `osv_vulnerabilities.py`. The agent is a prompt rather than code, so the offline pytest suite can't cover it. Its most important rules are about what it must *not* say: never call a package "safe" because OSV.dev has nothing on it (OSV answers an unknown or misspelled name exactly like a clean one), and lead with malware rather than treating it as a bug to upgrade past. Each case gives one fixed question chosen to exercise a rule.

These are live OSV.dev lookups. New advisories appear all the time, so counts and "lowest version that clears everything" change; the cases judge the agent's choices (name, ecosystem, version, framing), not the counts. Re-check a case's premise when it stops holding (e.g. if `requests` 2.33.0 gains an advisory, pick the newest clean version for case 2).

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "package-vulnerabilities"` and this prompt:

```text
{{Question}}

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<short-name>.out and NN-<short-name>.err (NN = the order you ran it), by redirecting, e.g. `python3 osv_vulnerabilities.py ... --json > DIR/01-osv.out 2> DIR/01-osv.err; echo "exit=$?"`, then read the files.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code, and saying why you chose that package name, version and ecosystem. Don't end with a question.
```

For case 4, add: "If your workflow says to ask the user something, don't ask: say in your report what you would have asked, and carry on with what the workflow allows without an answer." Check each run against the saved `.out` files (`count`, `complete`, each vulnerability's `severity`, `fixed`, `malicious`), above all any version the report tells the user to upgrade to.

## Cases

### 1. A vulnerable version, and what to upgrade to

- **Rule:** "Tell the user the lowest version that clears **all** listed vulnerabilities when the `fixed` lists make that clear (the highest of the per-vulnerability fixed versions within the same release line)."
- **Question:** `Does jinja2 2.4.1 have any vulnerabilities? What should I upgrade to?`
- **A correct run:** PyPI inferred; 9 vulnerabilities (3 high) merged from 18 advisories; 3.1.6 as the lowest version that clears all, with why no 2.x release does (the four newest are fixed only on 3.1.x) and a note that 2.x → 3.x is a major upgrade.
- **Last checked:** 2026-10-21, passed (fixed versions checked against the saved JSON).

### 2. No vulnerabilities: never "safe"

- **Rule:** "Don't call the package 'safe': no known advisory isn't a guarantee", and OSV answers a typo or wrong ecosystem the same way.
- **Question:** `Is requests 2.33.0 safe to use?` (OSV.dev had no advisory for it).
- **A correct run:** "no known vulnerabilities" for that version, explicitly not "safe", with the empty-answer-for-a-typo caveat and the usual published-advisories caveat.
- **Last checked:** 2026-10-21, passed.

### 3. A misspelled name

- **Rule:** the same empty-answer caveat, where it matters most.
- **Question:** `Is the Python package reqeusts safe to install? Any known vulnerabilities?`
- **A correct run:** looks the name up as typed (0 results), says that doesn't make it safe, flags the likely misspelling of `requests` and the typosquatting risk, advises against installing the misspelled name, and looks up `requests` as well.
- **Last checked:** 2026-10-21, passed.

### 4. A name in several registries

- **Rule:** "if it is genuinely ambiguous (a name that exists in several registries), ask or say which one you assumed."
- **Question:** `Does the colors package have any known vulnerabilities?` (npm's `colors` has two HIGH advisories from the January 2022 sabotage; PyPI's has none).
- **A correct run:** says what it would have asked, assumes npm and says so at the top, reports both advisories with no fixed version, and labels any pinning advice as its own reading of the advisory text rather than a listed fix.
- **Idea from 2026-10-21:** the agent didn't also look up the PyPI package, which would have shown its empty result. Not required by the rules; worth adding if ambiguous names turn out to confuse users.
- **Last checked:** 2026-10-21, passed.

### 5. Malware

- **Rule:** "Malicious entries (`malicious: true`): lead with this — the package (or version) was published as malware; advise removing it rather than upgrading."
- **Question:** `We use flatmap-stream in our Node app. Are there any security problems with it?` (npm; `MAL-2025-20690` plus two critical GitHub advisories, none with a fix).
- **A correct run:** opens with "remove it, it is malware", says there is nothing to upgrade to, and passes on the advisory's own remedy (check for `event-stream` 3.3.6; use 3.3.4 or 4.x).
- **Last checked:** 2026-10-21, passed.

### 6. No version given

- **Rules:** the Maven `group:artifact` name; "No version given: say this is every advisory for any version of the package, and point out which ones are recent."
- **Question:** `What vulnerabilities has log4j-core had over the years?`
- **A correct run:** `org.apache.logging.log4j:log4j-core` on Maven; all 11 advisories with the Log4Shell group named, the four from the past year pointed out, and 2.25.4 as the version that clears all on the 2.x line (the 2.12.x / 2.3.x backports don't cover the newest ones).
- **Last checked:** 2026-10-21, passed.

### 7. The fix for one named bug

- **Rules:** the Go module path and ecosystem; find the right advisory among many and give its fixed version.
- **Question:** `Which version of golang.org/x/net fixes the HTTP/2 rapid reset bug?`
- **A correct run:** `golang.org/x/net` on Go with no version; 0.17.0 for both CVE-2023-44487 and CVE-2023-39325, kept apart from the 2019 "reset flood" advisory, plus a note that 0.60.0 is the version that clears all 36 listed.
- **Last checked:** 2026-10-21, passed (0.17.0 and 0.60.0 checked against the saved JSON).

## Not covered

- A Linux distribution package (`Debian:12`, `Ubuntu:22.04:LTS`), where the ecosystem needs a release.
- A wrong ecosystem name (`400: invalid ecosystem`), which the agent should correct once.
- `complete: false`, which only happens for very large packages such as a distribution's kernel.
