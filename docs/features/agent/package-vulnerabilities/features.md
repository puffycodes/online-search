# Package Vulnerabilities

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the osv_vulnerabilities.py script to look up vulnerabilities in OSV.dev.

## Actions

- Take one or more open-source packages named by the user, each optionally with a version.
    - Use the name as its registry spells it (e.g. a Go module path, a Maven group:artifact, a scoped npm name). If unsure of the exact name, say so rather than guess.
    - Infer the ecosystem from the user's wording (e.g. "Python package" → PyPI, "npm package" → npm, a Linux distribution with its release → Debian:12); if a name is genuinely ambiguous across registries, ask or say which one was assumed.
    - With a version, check that version; without one, list every advisory for any version.
- Look up each package separately.
    - If the ecosystem name is rejected, fix an obviously wrong name once; otherwise report the error.
    - Retry at most once, only for a transient network error.
- Output:
    - The answer first: {{Package}} {{Version}} ({{Ecosystem}}) has {{Count}} known vulnerabilities, with how many are rated high or critical.
    - The most important ones: {{Severity}}, {{ID}} with its CVE, a one-line summary, the version that fixes it, and its osv.dev link. Use a table (Severity, ID, CVE, Summary, Fixed in) for more than about five, saying how many were left out.
    - The lowest version that clears every listed vulnerability, when the fixed versions make it clear; otherwise the fix for each one.
    - A malicious-package entry first and prominently: the package or version is malware; remove it rather than upgrade.
    - With no vulnerabilities: OSV.dev has none on record, noting that a misspelled name or wrong ecosystem gives the same empty answer. Never call the package safe.
    - Without a version: say these are all advisories for any version, and point out the recent ones.
    - Say a list is partial when OSV had more results than were fetched.
    - Report severity as the advisory's own rating, or "unrated"; never compute or invent one.
    - A credit line naming OSV.dev and the source databases of the advisories reported (their data is mostly CC-BY 4.0, which requires attribution).
    - A short caveat: this covers published advisories at the time of the lookup, not undisclosed issues, and whether a vulnerability affects a project depends on how it uses the package.
- Never fabricate vulnerabilities, ids, severities or fixed versions.
