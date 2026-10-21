#!/usr/bin/env python3
"""
Check every link on a web page and report the broken ones.

Fetches the page and extracts its links with url_links.fetch_links(), then
checks each one with url_availability.check_url() (an HTTP GET, following
redirects) and sorts it as ok, redirected, broken (a 4xx/5xx status other
than the ones below), blocked (401, 403 or 429: the server refused this
client, so the link may still work in a browser), or unreachable (DNS
failure, timeout, refused connection). With --wayback, each broken or
unreachable link is also looked up in the Wayback Machine through
url_availability.add_wayback().

Built to be polite on big pages:
- only http(s) links are checked, each URL once (fragments dropped), and
  links back to the page itself are skipped;
- at most --max-links links are checked (default 100), in page order;
- requests to the same host start at least --delay seconds apart
  (default 1.0);
- each linked host's robots.txt is read once (robots.py), and a link it
  disallows for this script is skipped, not fetched. An unreadable
  robots.txt counts as a full disallow (RFC 9309), except that a host that
  can't be connected to at all is reported as unreachable;
- Wayback lookups start at least 3 seconds apart and stop at the first
  rate-limit answer.

A redirect from a specific page to a site's front page is flagged in a
note, since that is how removed pages and parked domains usually look.

The page itself is the user's choice, so it is fetched regardless; its
robots.txt is only reported on, as url_content.py --warn-robots does
(ai_input_warning, robots_disallow_note).

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report. A page with broken links is a normal result (exit 0);
only a failure to fetch the page itself exits 1.
"""

import argparse
import json
import time
from urllib.parse import urldefrag, urlsplit

import requests

import robots
import url_availability
import url_links
from cli_utils import bounded_int, die, positive_int, use_utf8_output, validate_url_scheme

TIMEOUT_SECONDS = 10
MAX_LINKS = 100
MAX_LINKS_LIMIT = 1000
DELAY_SECONDS = 1.0
USER_AGENT = "Mozilla/5.0 (compatible; online-search-url-broken-links/1.0)"
# The product token matched against robots.txt User-agent groups.
ROBOTS_TOKEN = "online-search-url-broken-links"
# Statuses that mean "not for this client" rather than "gone".
BLOCKED_STATUSES = {401, 403, 429}
WAYBACK_HOST = "archive.org"
# The availability API rate-limits quickly (HTTP 429), so its lookups are
# spaced further apart than --delay, and stop at the first 429.
WAYBACK_DELAY = 3.0
# robots.fetch() problems that mean the host itself couldn't be reached (DNS
# failure, refused connection, connect timeout). Any other unreadable
# robots.txt counts as a full disallow (RFC 9309), so the link isn't fetched.
UNREACHABLE_ROBOTS_ERRORS = ("(ConnectionError)", "(ConnectTimeout)")

STATUSES = ("ok", "redirected", "broken", "blocked", "unreachable", "skipped_robots")
SKIP_REASONS = ("non_http", "same_page", "duplicates", "out_of_scope", "over_cap")


def non_negative_float(value):
    """argparse ``type`` for a number of seconds that must be 0 or more."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}")
    if number < 0:
        raise argparse.ArgumentTypeError(f"must be 0 or greater, got {number}")
    return number


def host_of(url):
    return urlsplit(url).netloc.lower()


class HostThrottle:
    """Spaces the start of requests to the same host at least ``delay`` seconds apart."""

    def __init__(self, delay):
        self.delay = delay
        self.last = {}

    def wait(self, host):
        last = self.last.get(host)
        if last is not None:
            gap = self.delay - (time.monotonic() - last)
            if gap > 0:
                time.sleep(gap)
        self.last[host] = time.monotonic()


class RobotsCache:
    """Each host's robots.txt, fetched once (through the throttle) and parsed."""

    def __init__(self, throttle, timeout):
        self.throttle = throttle
        self.timeout = timeout
        self.hosts = {}

    def get(self, url):
        """Return ``(groups, global_signals, problem)`` for ``url``'s host.

        ``problem`` is None, or robots.fetch()'s reason the file couldn't be read.
        """
        host = host_of(url)
        if host not in self.hosts:
            self.throttle.wait(host)
            text, problem = robots.fetch(url, USER_AGENT, self.timeout)
            groups, signals = robots.parse(text) if problem is None else ([], [])
            self.hosts[host] = (groups, signals, problem)
        return self.hosts[host]


def select_links(links, page_url, scope, max_links):
    """Pick the links to check from url_links' ``links``, in page order.

    Returns ``(selected, skipped)``: ``selected`` is a list of {url, text,
    internal} with fragments dropped, ``skipped`` counts what was left out
    and why (see SKIP_REASONS). ``internal`` means the same host as the page.
    """
    page = urldefrag(page_url)[0]
    page_host = host_of(page_url)
    seen, selected = set(), []
    skipped = dict.fromkeys(SKIP_REASONS, 0)
    for link in links:
        url = urldefrag(link["url"])[0]
        if urlsplit(url).scheme.lower() not in ("http", "https"):
            skipped["non_http"] += 1
            continue
        if url == page:
            skipped["same_page"] += 1
            continue
        if url in seen:
            skipped["duplicates"] += 1
            continue
        seen.add(url)
        internal = host_of(url) == page_host
        if (scope == "internal" and not internal) or (scope == "external" and internal):
            skipped["out_of_scope"] += 1
            continue
        if len(selected) >= max_links:
            skipped["over_cap"] += 1
            continue
        selected.append({"url": url, "text": link["text"], "internal": internal})
    return selected, skipped


def classify(status_code, url, final_url):
    if status_code < 400:
        return "ok" if final_url == url else "redirected"
    if status_code in BLOCKED_STATUSES:
        return "blocked"
    return "broken"


def check_link(link, robots_cache, throttle, timeout):
    """Check one selected link and return its record (see STATUSES)."""
    record = dict(link, status=None, status_code=None, reason=None, final_url=None,
                  error=None, note=None)
    url = link["url"]
    groups, _, problem = robots_cache.get(url)
    if problem:
        unreachable = problem.endswith(UNREACHABLE_ROBOTS_ERRORS)
        record.update(status="unreachable" if unreachable else "skipped_robots",
                      error=f"{host_of(url)}: {problem}")
        return record
    if not robots.is_allowed(groups, ROBOTS_TOKEN, robots.url_path(url)):
        record.update(status="skipped_robots",
                      error=f"{host_of(url)}'s robots.txt disallows {robots.url_path(url)}")
        return record

    throttle.wait(host_of(url))
    try:
        checked = url_availability.check_url(url, timeout=timeout, user_agent=USER_AGENT)
    except requests.RequestException as exc:
        record.update(status="unreachable", error=str(exc) or type(exc).__name__)
        return record
    record.update(
        status=classify(checked["status_code"], url, checked["final_url"]),
        status_code=checked["status_code"],
        reason=checked["reason"],
        final_url=checked["final_url"],
    )
    if record["status"] == "redirected" and lands_on_home_page(url, checked["final_url"]):
        record["note"] = "redirects to a home page; the linked page may be gone"
    return record


def lands_on_home_page(url, final_url):
    """Whether a link to a specific page redirected to a site's front page,
    the usual sign of a removed page or a parked domain."""
    def is_root(u):
        return urlsplit(u).path in ("", "/") and not urlsplit(u).query
    return not is_root(url) and is_root(final_url)


def add_wayback_copies(records, throttle, timeout):
    """Look up Wayback copies for the broken and unreachable records.

    Stops after the first rate-limit answer (HTTP 429): the rest get an
    archive_error saying they weren't looked up.
    """
    rate_limited = False
    for record in records:
        if record["status"] not in ("broken", "unreachable"):
            continue
        if rate_limited:
            record["archived"] = None
            record["archive_error"] = "not looked up: the Wayback Machine rate-limited an earlier lookup"
            continue
        throttle.wait(WAYBACK_HOST)
        url_availability.add_wayback(record, timeout=timeout)
        rate_limited = "429" in (record["archive_error"] or "")


def page_notes(robots_cache, page_url):
    """robots.review()'s notes for the page, from the cached robots.txt."""
    notes = {"ai_input_warning": None, "robots_disallow_note": None}
    groups, signals, problem = robots_cache.get(page_url)
    if problem:
        return notes
    host, path = host_of(page_url), robots.url_path(page_url)
    if not robots.ai_input_allowed(groups, signals, ROBOTS_TOKEN, path):
        notes["ai_input_warning"] = (
            f"{host}'s robots.txt opts out of AI input (Content-Signal: ai-input=no)"
        )
    if not robots.is_allowed(groups, ROBOTS_TOKEN, path):
        notes["robots_disallow_note"] = (
            f"{host}'s robots.txt asks automated clients not to fetch {path}"
        )
    return notes


def check_page(url, max_links=MAX_LINKS, delay=DELAY_SECONDS, scope="all",
               wayback=False, timeout=TIMEOUT_SECONDS):
    """Fetch ``url``, check its links, and return the full result dict.

    Raises what url_links.fetch_links() raises when the page itself can't be
    fetched or isn't HTML.
    """
    throttle = HostThrottle(delay)
    robots_cache = RobotsCache(throttle, timeout)

    throttle.wait(host_of(url))
    page = url_links.fetch_links(url, timeout=timeout, user_agent=USER_AGENT)
    selected, skipped = select_links(page["links"], page["final_url"], scope, max_links)

    records = [check_link(link, robots_cache, throttle, timeout) for link in selected]
    if wayback:
        add_wayback_copies(records, HostThrottle(max(delay, WAYBACK_DELAY)), timeout)

    counts = dict.fromkeys(STATUSES, 0)
    for record in records:
        counts[record["status"]] += 1
    result = {
        "url": url,
        "final_url": page["final_url"],
        "link_count": page["link_count"],
        "checked": len(records),
        "max_links": max_links,
        "scope": scope,
        "counts": counts,
        "skipped": skipped,
    }
    result.update(page_notes(robots_cache, page["final_url"]))
    result["links"] = records
    return result


def _link_line(record):
    text = f'  "{record["text"]}"' if record["text"] else ""
    if record["status_code"] is not None:
        return f"  {record['status_code']} {record['reason'] or ''}".rstrip() + f"  {record['url']}{text}"
    return f"  {record['url']}{text}\n    {record['error']}"


def _archive_line(record):
    if "archived" not in record:
        return None
    if record["archive_error"]:
        return f"    Archived copy: lookup failed ({record['archive_error']})"
    if record["archived"] is None:
        return "    Archived copy: none found in the Wayback Machine"
    return f"    Archived copy: {record['archived']['url']}"


def format_result(result, show_ok=False):
    """The text report: problem links, then redirects, then (with ``show_ok``)
    the links that worked."""
    lines = [f"Page: {result['url']}"]
    if result["final_url"] != result["url"]:
        lines.append(f"Redirected to: {result['final_url']}")
    for key in ("ai_input_warning", "robots_disallow_note"):
        if result[key]:
            lines.append(f"Note: {result[key]}")

    skipped = result["skipped"]
    skip_bits = [
        f"{skipped['non_http']} non-web",
        f"{skipped['same_page']} back to this page",
        f"{skipped['duplicates']} duplicate",
        f"{skipped['out_of_scope']} outside --scope {result['scope']}",
        f"{skipped['over_cap']} over the cap of {result['max_links']}",
    ]
    skip_text = ", ".join(bit for bit, n in zip(skip_bits, skipped.values()) if n)
    lines.append(
        f"Links found: {result['link_count']}; checked: {result['checked']}"
        + (f" (left out: {skip_text})" if skip_text else "")
    )
    counts = result["counts"]
    lines.append(
        f"Result: {counts['ok']} ok, {counts['redirected']} redirected, "
        f"{counts['broken']} broken, {counts['blocked']} blocked, "
        f"{counts['unreachable']} unreachable, {counts['skipped_robots']} skipped by robots.txt"
    )

    sections = [
        ("broken", "Broken"),
        ("unreachable", "Unreachable"),
        ("blocked", "Blocked (refused this client; may work in a browser)"),
        ("skipped_robots", "Not checked (robots.txt disallows it or couldn't be read)"),
    ]
    for status, title in sections:
        group = [r for r in result["links"] if r["status"] == status]
        if not group:
            continue
        lines += ["", f"{title} ({len(group)}):"]
        for record in group:
            lines.append(_link_line(record))
            archive = _archive_line(record)
            if archive:
                lines.append(archive)
    redirected = [r for r in result["links"] if r["status"] == "redirected"]
    if redirected:
        lines += ["", f"Redirected ({len(redirected)}):"]
        for record in redirected:
            lines.append(f"  {record['url']}\n    -> {record['final_url']}")
            if record.get("note"):
                lines.append(f"    Note: {record['note']}")
    ok = [r for r in result["links"] if r["status"] == "ok"] if show_ok else []
    if ok:
        lines += ["", f"OK ({len(ok)}):"]
        lines += [_link_line(record) for record in ok]
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Check every link on a web page and report the broken ones."
    )
    parser.add_argument("url", help="Page to check, e.g. https://example.com/docs")
    parser.add_argument(
        "--max-links",
        type=bounded_int(MAX_LINKS_LIMIT),
        default=MAX_LINKS,
        metavar="N",
        help=f"Check at most N links, in page order (default: {MAX_LINKS}, at most {MAX_LINKS_LIMIT})",
    )
    parser.add_argument(
        "--delay",
        type=non_negative_float,
        default=DELAY_SECONDS,
        metavar="SECONDS",
        help=f"Minimum gap between requests to the same host (default: {DELAY_SECONDS})",
    )
    parser.add_argument(
        "--scope",
        choices=("all", "internal", "external"),
        default="all",
        help="Check every link, only links to the page's own host, or only links elsewhere "
             "(default: all)",
    )
    parser.add_argument(
        "--wayback",
        action="store_true",
        help="Look up the most recent Wayback Machine copy of each broken or unreachable link.",
    )
    parser.add_argument(
        "--show-ok",
        action="store_true",
        help="Also list the links that worked in the text report (--json always includes them).",
    )
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=TIMEOUT_SECONDS,
        help=f"Request timeout in seconds (default: {TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    validate_url_scheme(args.url, args.json)

    if not args.json:
        print(f"Checking the links on: {args.url}\n")

    try:
        result = check_page(
            args.url, max_links=args.max_links, delay=args.delay, scope=args.scope,
            wayback=args.wayback, timeout=args.timeout,
        )
    except ImportError:
        die("beautifulsoup4 is required (pip install beautifulsoup4)", args.json)
    except (requests.RequestException, ValueError) as exc:
        die(f"couldn't fetch the page: {exc}", args.json)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result, show_ok=args.show_ok))


if __name__ == "__main__":
    main()
