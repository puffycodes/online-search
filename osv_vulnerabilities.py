#!/usr/bin/env python3
"""
Look up the known security vulnerabilities of a package - optionally at one
version - in OSV.dev, Google's open, distributed vulnerability database
covering PyPI, npm, Go, crates.io, Maven, NuGet, RubyGems, Packagist, Debian
and many more ecosystems. No API key or authentication required.

Give it a package name, optionally a version, and --ecosystem. Without a
version, every advisory that affects any version of the package is listed.
The ecosystem is matched case-insensitively against OSV's own names (PyPI,
npm, Go, crates.io, ...), with a few everyday aliases (pip, cargo, gem, ...);
a release suffix such as Debian:12 is kept as given.

OSV often holds the same vulnerability twice - e.g. a GitHub advisory
(GHSA-...) and a PyPI one (PYSEC-...) that list each other as aliases. Those
are merged into one entry that names every advisory and its source database.
The data is licensed per source (mostly CC-BY 4.0), so the output always
credits each advisory's source and links its osv.dev page.

OSV answers an unknown package exactly as it answers a clean one (no
vulnerabilities), so an empty result can also mean a misspelled name.

Supports --json for structured output so an agent can parse stdout instead
of the human-readable report. On failure the process exits non-zero and
prints {"error": "..."} to stderr.
"""

import argparse
import json
import re

import requests

from cli_utils import die, positive_int, use_utf8_output

QUERY_URL = "https://api.osv.dev/v1/query"
VULN_PAGE_URL = "https://osv.dev/vulnerability/{id}"
REQUEST_TIMEOUT = 30
# Pages of results to follow (OSV pages large result sets, e.g. Debian's
# linux package, with next_page_token). A cap keeps one lookup polite.
MAX_PAGES = 5
DEFAULT_LIMIT = 50
DETAILS_CHARS = 400

# OSV's ecosystem names, from
# https://osv-vulnerabilities.storage.googleapis.com/ecosystems.txt
ECOSYSTEMS = [
    "AlmaLinux", "Alpaquita", "Alpine", "Android", "Azure Linux",
    "BellSoft Hardened Containers", "Bitnami", "CRAN", "Chainguard",
    "CleanStart", "Debian", "Echo", "GHC", "GIT", "GSD", "GitHub Actions",
    "Go", "Hackage", "Hex", "Julia", "Linux", "Mageia", "Maven", "MinimOS",
    "NuGet", "OSS-Fuzz", "Packagist", "Pub", "PyPI", "Red Hat",
    "Rocky Linux", "Root", "RubyGems", "SUSE", "SwiftURL", "TuxCare", "UVI",
    "Ubuntu", "VSCode", "Wolfi", "crates.io", "npm", "opam", "openEuler",
    "openSUSE",
]
ECOSYSTEM_ALIASES = {
    "pip": "PyPI", "python": "PyPI",
    "node": "npm", "nodejs": "npm", "javascript": "npm",
    "golang": "Go",
    "cargo": "crates.io", "rust": "crates.io", "crates": "crates.io",
    "gem": "RubyGems", "gems": "RubyGems", "ruby": "RubyGems",
    "composer": "Packagist", "php": "Packagist",
    "dotnet": "NuGet", ".net": "NuGet",
    "java": "Maven",
    "dart": "Pub", "flutter": "Pub",
    "elixir": "Hex", "erlang": "Hex",
    "haskell": "Hackage",
    "r": "CRAN",
}

# Advisory-id prefix -> the database that published it, for attribution.
SOURCES = {
    "GHSA": "GitHub Advisory Database",
    "PYSEC": "PyPI Advisory Database",
    "PSF": "Python Software Foundation",
    "GO": "Go Vulnerability Database",
    "RUSTSEC": "RustSec Advisory Database",
    "OSV": "OSS-Fuzz",
    "GSD": "Global Security Database",
    "MAL": "OpenSSF Malicious Packages",
    "HSEC": "Haskell Security Advisories",
    "RSEC": "R Consortium Advisory Database",
    "BIT": "Bitnami Vulnerability Database",
    "EEF": "Erlang Ecosystem Foundation CNA",
    "DRUPAL": "Drupal Advisory Database",
    "USN": "Ubuntu", "UBUNTU": "Ubuntu",
    "DSA": "Debian", "DLA": "Debian", "DTSA": "Debian", "DEBIAN": "Debian",
    "ALSA": "AlmaLinux", "ALBA": "AlmaLinux", "ALEA": "AlmaLinux",
    "RLSA": "Rocky Linux",
    "CGA": "Chainguard",
    "SUSE": "SUSE", "openSUSE": "openSUSE",
    "RHSA": "Red Hat", "RHBA": "Red Hat", "RHEA": "Red Hat",
    "MGASA": "Mageia",
    "ALPINE": "Alpine",
    "CVE": "CVE (via OSV.dev)",
}
SEVERITY_ORDER = ["CRITICAL", "HIGH", "MODERATE", "MEDIUM", "LOW"]
ATTRIBUTION = (
    "Data from OSV.dev (https://osv.dev), which aggregates the advisory "
    "databases named on each entry; each source's own licence applies "
    "(mostly CC-BY 4.0)."
)


def canonical_ecosystem(value):
    """OSV's spelling of an ecosystem name, matched case-insensitively.

    A release suffix after the first colon (Debian:12, Ubuntu:22.04:LTS) is
    kept as given. Unknown names are returned unchanged for OSV to judge.
    """
    base, sep, release = value.strip().partition(":")
    key = base.strip().lower()
    for name in ECOSYSTEMS:
        if name.lower() == key:
            return name + sep + release
    return ECOSYSTEM_ALIASES.get(key, base.strip()) + sep + release


def source_name(vuln_id):
    """The database an advisory id came from, by its prefix (GHSA-..., PYSEC-...)."""
    prefix = vuln_id.split("-", 1)[0]
    return SOURCES.get(prefix) or SOURCES.get(prefix.upper()) or prefix


def post_query(payload):
    """POST one /v1/query and return its JSON body.

    Raises requests.HTTPError carrying OSV's own message (e.g. "invalid
    ecosystem") on an error status.
    """
    response = requests.post(QUERY_URL, json=payload, timeout=REQUEST_TIMEOUT)
    if not response.ok:
        try:
            message = response.json().get("message")
        except (ValueError, AttributeError):
            message = None
        if message:
            raise requests.HTTPError(f"{response.status_code}: {message}", response=response)
    response.raise_for_status()
    return response.json()


def fetch_vulns(package, ecosystem, version=None, max_pages=MAX_PAGES):
    """All OSV records for the package (at version, if given).

    Returns (vulns, complete): complete is False when more pages remained
    after max_pages.
    """
    payload = {"package": {"name": package, "ecosystem": ecosystem}}
    if version:
        payload["version"] = version
    vulns = []
    for _ in range(max_pages):
        body = post_query(payload)
        vulns.extend(body.get("vulns") or [])
        token = body.get("next_page_token")
        if not token:
            return vulns, True
        payload["page_token"] = token
    return vulns, False


def group_vulns(vulns):
    """Group records that name each other as aliases (GHSA-x and PYSEC-y for one bug).

    Returns a list of record lists, in order of each group's first record.
    """
    parent = {}

    def find(key):
        while parent.setdefault(key, key) != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    ids = {v["id"] for v in vulns}
    for v in vulns:
        for alias in v.get("aliases") or []:
            # Only link through ids that came back in this result, so a shared
            # alias outside it (e.g. one CVE) still merges, but nothing else.
            if alias in ids or alias.startswith("CVE-"):
                parent[find(alias)] = find(v["id"])

    groups = {}
    for v in vulns:
        groups.setdefault(find(v["id"]), []).append(v)
    return list(groups.values())


def _normalize_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def fixed_versions(records, package, ecosystem):
    """Versions that fix the bug for this package, in the order OSV lists them.

    Read from each record's ECOSYSTEM / SEMVER ranges (GIT ranges hold
    commit hashes, not versions).
    """
    base = ecosystem.split(":", 1)[0].lower()
    want = _normalize_name(package)
    out = []
    for record in records:
        for affected in record.get("affected") or []:
            pkg = affected.get("package") or {}
            if _normalize_name(pkg.get("name", "")) != want:
                continue
            if pkg.get("ecosystem", "").split(":", 1)[0].lower() != base:
                continue
            for rng in affected.get("ranges") or []:
                if rng.get("type") not in ("ECOSYSTEM", "SEMVER"):
                    continue
                for event in rng.get("events") or []:
                    fixed = event.get("fixed")
                    if fixed and fixed not in out:
                        out.append(fixed)
    return out


def _clip(text, limit=DETAILS_CHARS):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def summarize_group(records, package, ecosystem):
    """One merged vulnerability as a JSON-ready dict."""
    records = sorted(records, key=lambda r: (
        not r["id"].startswith("GHSA-"), not r.get("summary"), r["id"]))
    primary = records[0]
    ids = [r["id"] for r in records]
    aliases = sorted({a for r in records for a in r.get("aliases") or []} - set(ids))
    summary = next((r["summary"] for r in records if r.get("summary")), None)
    details = next((r["details"] for r in records if r.get("details")), "")
    severity = next(
        ((r.get("database_specific") or {}).get("severity") for r in records
         if isinstance((r.get("database_specific") or {}).get("severity"), str)),
        None,
    )
    cvss = []
    for record in records:
        for entry in record.get("severity") or []:
            item = {"type": entry.get("type"), "vector": entry.get("score")}
            if item not in cvss:
                cvss.append(item)
    published = [r["published"] for r in records if r.get("published")]
    modified = [r["modified"] for r in records if r.get("modified")]
    return {
        "id": primary["id"],
        "url": VULN_PAGE_URL.format(id=primary["id"]),
        "summary": summary or _clip(details, 120) or None,
        "details": _clip(details) or None,
        "severity": severity.upper() if severity else None,
        "cvss": cvss,
        "cve": [a for a in aliases if a.startswith("CVE-")],
        "aliases": aliases,
        "malicious": any(i.startswith("MAL-") for i in ids),
        "fixed": fixed_versions(records, package, ecosystem),
        "published": min(published)[:10] if published else None,
        "modified": max(modified)[:10] if modified else None,
        "advisories": [
            {"id": i, "source": source_name(i), "url": VULN_PAGE_URL.format(id=i)}
            for i in ids
        ],
    }


def _severity_rank(item):
    """Malicious packages first, then CRITICAL ... LOW, then unrated."""
    if item["severity"] in SEVERITY_ORDER:
        rank = SEVERITY_ORDER.index(item["severity"])
    else:
        rank = len(SEVERITY_ORDER)
    return (not item["malicious"], rank)


def build_results(vulns, package, ecosystem):
    """Merged, sorted vulnerabilities, skipping groups that are all withdrawn."""
    items = []
    for records in group_vulns(vulns):
        live = [r for r in records if not r.get("withdrawn")]
        if live:
            items.append(summarize_group(live, package, ecosystem))
    # Newest first, then a stable sort by severity keeps that order within each.
    items.sort(key=lambda item: item["published"] or "", reverse=True)
    items.sort(key=_severity_rank)
    return items


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Look up a package's known vulnerabilities in OSV.dev.",
    )
    parser.add_argument("package", help="Package name, e.g. jinja2, lodash, golang.org/x/net")
    parser.add_argument(
        "version", nargs="?",
        help="Version to check, e.g. 2.4.1 (default: every advisory for the package)",
    )
    parser.add_argument(
        "-e", "--ecosystem", required=True,
        help="Package ecosystem: PyPI, npm, Go, crates.io, Maven, NuGet, RubyGems, "
             "Packagist, Debian:12, ... (case-insensitive; pip, cargo, gem, ... also work)",
    )
    parser.add_argument(
        "--limit", type=positive_int, default=DEFAULT_LIMIT,
        help=f"Show at most N vulnerabilities, most severe first (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON on stdout instead of a human-readable report.",
    )
    args = parser.parse_args(argv)
    args.ecosystem = canonical_ecosystem(args.ecosystem)
    if not args.package.strip():
        parser.error("package name must not be empty")
    return args


def print_report(payload):
    target = payload["package"] + (f" {payload['version']}" if payload["version"] else "")
    eco = payload["ecosystem"]
    items = payload["vulnerabilities"]
    if not payload["count"]:
        scope = "this version" if payload["version"] else "any version"
        print(f"No known vulnerabilities in OSV.dev for {target} ({eco}), {scope}.")
        print("OSV gives the same empty answer for a package name it doesn't know - "
              "check the spelling and ecosystem.")
        print(f"\n{ATTRIBUTION}")
        return

    noun = "vulnerability" if payload["count"] == 1 else "vulnerabilities"
    scope = "" if payload["version"] else " (any version)"
    print(f"{target} ({eco}){scope}: {payload['count']} known {noun}"
          f" from {payload['advisories']} advisor{'y' if payload['advisories'] == 1 else 'ies'}\n")
    for item in items:
        label = "MALICIOUS" if item["malicious"] else (item["severity"] or "UNRATED")
        cve = f" ({', '.join(item['cve'])})" if item["cve"] else ""
        print(f"[{label}] {item['id']}{cve}")
        print(f"  {item['summary'] or '(no summary)'}")
        fixed = ", ".join(item["fixed"]) if item["fixed"] else "no fixed version listed"
        print(f"  fixed in: {fixed}  |  published {item['published'] or '?'}")
        sources = "; ".join(f"{a['id']} ({a['source']})" for a in item["advisories"])
        print(f"  advisories: {sources}")
        print(f"  {item['url']}\n")
    if payload["count"] > len(items):
        print(f"... and {payload['count'] - len(items)} more (raise --limit to see them)\n")
    if not payload["complete"]:
        print(f"Note: OSV had more results than the {MAX_PAGES} pages fetched; "
              "the count covers only those.\n")
    print(ATTRIBUTION)


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)
    target = args.package + (f" {args.version}" if args.version else "")
    if not args.json:
        print(f"Querying OSV.dev for {target} ({args.ecosystem})...\n")

    try:
        vulns, complete = fetch_vulns(args.package, args.ecosystem, args.version)
    except (requests.RequestException, ValueError) as exc:
        die(f"OSV.dev lookup failed for {target} ({args.ecosystem}): {exc}", args.json)

    items = build_results(vulns, args.package, args.ecosystem)
    payload = {
        "package": args.package,
        "version": args.version,
        "ecosystem": args.ecosystem,
        "count": len(items),
        "advisories": sum(len(i["advisories"]) for i in items),
        "complete": complete,
        "vulnerabilities": items[:args.limit],
        "attribution": ATTRIBUTION,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return
    print_report(payload)


if __name__ == "__main__":
    main()
