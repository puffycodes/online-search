#!/usr/bin/env python3
"""
Check whether a web page at a given URL is reachable, by making an HTTP GET
request and inspecting the response. A 4xx/5xx status counts as
unavailable, not just a connection failure - so a live server returning
"404 Not Found" is correctly reported as NOT AVAILABLE rather than treated
the same as an unreachable host.

GET (not HEAD) is used because some servers block or mishandle HEAD
requests, which would produce false negatives.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json
import time

import requests

from cli_utils import die, positive_int, validate_url_scheme

TIMEOUT_SECONDS = 10
USER_AGENT = "Mozilla/5.0 (compatible; online-search-url-availability/1.0)"


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


def format_result(result):
    lines = [f"URL: {result['url']}"]
    if result["final_url"] != result["url"]:
        lines.append(f"Redirected to: {result['final_url']}")
    status = "AVAILABLE" if result["available"] else "NOT AVAILABLE"
    lines.append(f"Status: {status} ({result['status_code']} {result['reason']})")
    lines.append(f"Response time: {result['elapsed_ms']} ms")
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
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    validate_url_scheme(args.url, args.json)

    if not args.json:
        print(f"Checking: {args.url}\n")

    try:
        result = check_url(args.url, timeout=args.timeout)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))


if __name__ == "__main__":
    main()
