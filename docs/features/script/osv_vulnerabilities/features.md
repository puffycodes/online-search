# OSV Vulnerabilities

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the OSV.dev API's query endpoint (https://api.osv.dev/v1/query; no API key).
    - Checked on 2026-10-20: its robots.txt blocks nothing and declares no AI opt-out; its data is licensed per source, mostly CC-BY 4.0, so every result must credit its source (see docs/things-to-explore.md).
- Use cli_utils.py's use_utf8_output(), die() and positive_int.

## Actions

- Run as python3 osv_vulnerabilities.py from the repo root.
- Take:
    - {{Package}}: the package name as its registry spells it, e.g. jinja2, lodash, golang.org/x/net, org.apache.logging.log4j:log4j-core. A blank name exits with code 2.
    - Optionally a {{Version}}, e.g. 2.4.1. Without one, list every advisory for any version of the package.
    - {{Ecosystem}} (required): PyPI, npm, Go, crates.io, Maven, NuGet, RubyGems, Packagist, Debian:12, ...
        - Match it case-insensitively against OSV's ecosystem names, and accept everyday aliases (pip, python → PyPI; node, javascript → npm; golang → Go; cargo, rust → crates.io; gem, ruby → RubyGems; composer, php → Packagist; ...).
        - Keep a release suffix after the first colon as given (Debian:12, Ubuntu:22.04:LTS).
        - Pass an unknown name through unchanged, for OSV to reject.
    - The maximum number of vulnerabilities to show (default: 50).
    - Optionally JSON output.
- Query OSV for the package (and version), following its page tokens for up to 5 pages; if more remain, mark the result incomplete.
- Merge advisories that are the same vulnerability: those that list each other as aliases, directly or through a chain, or that share a CVE id.
- Drop withdrawn advisories; drop a vulnerability whose advisories are all withdrawn.
- For each vulnerability, report:
    - Its main id (a GitHub GHSA advisory when there is one) and its osv.dev link.
    - A summary (the advisory's, or the start of its details), and the details cut to 400 characters.
    - The severity rating a source gave it (CRITICAL, HIGH, MODERATE, LOW), or none, and any CVSS vectors.
    - Its CVE ids and other aliases.
    - Whether it is a malicious-package (MAL-) entry.
    - The versions that fix it for this package, read from version ranges (not commit ranges).
    - The earliest published and latest modified dates.
    - Every merged advisory with the database that published it (from its id prefix: GHSA → GitHub Advisory Database, PYSEC → PyPI Advisory Database, GO → Go Vulnerability Database, RUSTSEC → RustSec Advisory Database, MAL → OpenSSF Malicious Packages, ...) and its osv.dev link.
- Order them malicious entries first, then CRITICAL, HIGH, MODERATE, LOW, unrated, newest first within each.
- Output:
    - "Querying OSV.dev for {{Package}} {{Version}} ({{Ecosystem}})...", then "{{Package}} {{Version}} ({{Ecosystem}}): {{Count}} known vulnerabilities from {{Advisories}} advisories", marking "(any version)" when no version was given.
    - For each vulnerability: [{{Severity}} or MALICIOUS or UNRATED] {{ID}} ({{CVEs}}), its summary, the fixed versions (or "no fixed version listed") and published date, its advisories with their sources, and its osv.dev link.
    - How many more there are beyond the limit, and a note when OSV had more pages than were fetched.
    - With no vulnerabilities: "No known vulnerabilities in OSV.dev for {{Package}} {{Version}} ({{Ecosystem}})", plus a warning that OSV gives the same answer for a package name it doesn't know.
    - Always end with the attribution line: the data is from OSV.dev, aggregating the named databases, each under its own licence (mostly CC-BY 4.0).
    - With JSON output: {package, version, ecosystem, count, advisories, complete, vulnerabilities, attribution}, with no progress line. The count is the total; the list is cut to the limit.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A network error or an error status (with OSV's own message, e.g. "400: invalid ecosystem") exits with code 1, with "Error: ..." on stderr, or {"error": "..."} with JSON output.
    - A missing package or ecosystem, or an invalid limit, exits with code 2, before any network call.
