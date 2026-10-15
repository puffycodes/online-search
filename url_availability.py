#!/usr/bin/env python3
"""
Check whether a web page at a given URL is reachable, by making an HTTP GET
request and inspecting the response. A 4xx/5xx status counts as
unavailable, not just a connection failure - so a live server returning
"404 Not Found" is correctly reported as NOT AVAILABLE rather than treated
the same as an unreachable host.

GET (not HEAD) is used because some servers block or mishandle HEAD
requests, which would produce false negatives.

With --wayback, a page that isn't available (a 4xx/5xx status, or no
response at all) is also looked up in the Internet Archive's Wayback
Machine, and its most recent archived copy is reported.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json
import time
from datetime import datetime

import requests

from cli_utils import die, positive_int, use_utf8_output, validate_url_scheme

TIMEOUT_SECONDS = 10
USER_AGENT = "Mozilla/5.0 (compatible; online-search-url-availability/1.0)"
WAYBACK_API_URL = "https://archive.org/wayback/available"


def check_url(url, timeout=TIMEOUT_SECONDS):
    """GET `url` and report whether it's available.

    Returns a dict with url, available, status_code, reason, final_url
    (after redirects), and elapsed_ms. HTTP-level errors (4xx/5xx) are
    reported as available=False rather than raised; only connection-level
    failures (DNS, timeout, refused connection, ...) propagate as
    requests.RequestException for the caller to handle.
    """
    headers = {"User-Agent": USER_AGENT}
    start = time.monotonic()
    response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    elapsed_ms = round((time.monotonic() - start) * 1000)
    return {
        "url": url,
        "available": response.status_code < 400,
        "status_code": response.status_code,
        "reason": response.reason,
        "final_url": response.url,
        "elapsed_ms": elapsed_ms,
    }


def unreachable_result(url, error):
    """The record for a URL whose request failed at the connection level.

    Only used with --wayback, where a connection failure is reported (so
    the archived copy can be shown) instead of ending the script.
    """
    return {
        "url": url,
        "available": False,
        "status_code": None,
        "reason": None,
        "final_url": None,
        "elapsed_ms": None,
        "error": str(error),
    }


def fetch_wayback(url, timeout=TIMEOUT_SECONDS):
    """Look up the most recent Wayback Machine snapshot of `url`.

    Returns {url, timestamp, archived_at, status} for the snapshot, or None
    if the archive has no copy. `timestamp` is the archive's raw
    YYYYMMDDhhmmss (UTC) value and `archived_at` the same moment in ISO 8601;
    `status` is the HTTP status the page returned when it was archived, so a
    snapshot isn't necessarily a working copy. Request failures (including
    the archive's 429 rate limiting) propagate as requests.RequestException,
    and a non-JSON body as ValueError.
    """
    response = requests.get(
        WAYBACK_API_URL,
        params={"url": url},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()
    closest = (response.json().get("archived_snapshots") or {}).get("closest")
    if not closest or not closest.get("available"):
        return None
    timestamp = closest.get("timestamp")
    try:
        archived_at = datetime.strptime(timestamp, "%Y%m%d%H%M%S").strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (TypeError, ValueError):
        archived_at = None
    status = closest.get("status")
    return {
        "url": closest.get("url"),
        "timestamp": timestamp,
        "archived_at": archived_at,
        "status": int(status) if isinstance(status, str) and status.isdigit() else status,
    }


def add_wayback(result, timeout=TIMEOUT_SECONDS):
    """Add `archived` and `archive_error` to `result` from a Wayback lookup.

    A failed lookup doesn't fail the check: `archived` is None and
    `archive_error` says why, so the dead-link finding is still reported.
    """
    try:
        result["archived"] = fetch_wayback(result["url"], timeout=timeout)
        result["archive_error"] = None
    except (requests.RequestException, ValueError) as exc:
        result["archived"] = None
        result["archive_error"] = str(exc) or type(exc).__name__
    return result


def format_result(result):
    lines = [f"URL: {result['url']}"]
    if result.get("error"):
        lines.append(f"Status: NOT REACHABLE ({result['error']})")
    else:
        if result["final_url"] != result["url"]:
            lines.append(f"Redirected to: {result['final_url']}")
        status = "AVAILABLE" if result["available"] else "NOT AVAILABLE"
        lines.append(f"Status: {status} ({result['status_code']} {result['reason']})")
        lines.append(f"Response time: {result['elapsed_ms']} ms")
    if "archived" in result:
        archived = result["archived"]
        if result["archive_error"]:
            lines.append(f"Archived copy: lookup failed ({result['archive_error']})")
        elif archived is None:
            lines.append("Archived copy: none found in the Wayback Machine")
        else:
            if archived["archived_at"]:
                when = archived["archived_at"].replace("T", " ").replace("Z", " UTC")
            else:
                when = archived["timestamp"]
            lines.append(f"Archived copy: {archived['url']}")
            lines.append(f"  Archived {when}; page status then: {archived['status']}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Check whether a web page at a given URL is available."
    )
    parser.add_argument("url", help="URL to check, e.g. https://example.com")
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=TIMEOUT_SECONDS,
        help=f"Request timeout in seconds (default: {TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--wayback",
        action="store_true",
        help="If the page isn't available, also look up its most recent "
        "archived copy in the Wayback Machine.",
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
        print(f"Checking: {args.url}\n")

    try:
        result = check_url(args.url, timeout=args.timeout)
    except requests.RequestException as exc:
        if not args.wayback:
            die(str(exc), args.json)
        result = unreachable_result(args.url, exc)

    if args.wayback and not result["available"]:
        add_wayback(result, timeout=args.timeout)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))


if __name__ == "__main__":
    main()
