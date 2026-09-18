#!/usr/bin/env python3
"""
Retrieve a web page at a given URL and extract all the hyperlinks in its
HTML content.

Parses every ``<a href="...">`` tag via BeautifulSoup and resolves each
href against the page's final URL (after redirects), so relative links
(``/about``, ``../docs``) come back as absolute URLs alongside the link's
visible text. Anchors with no ``href`` attribute are skipped; everything
else (including ``mailto:``, ``tel:``, and ``javascript:`` links) is kept
as-is, since filtering those is a caller decision.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json
from urllib.parse import urljoin

import requests

from cli_utils import die, positive_int

TIMEOUT_SECONDS = 10
USER_AGENT = "Mozilla/5.0 (compatible; online-search-url-links/1.0)"


def extract_links(html, base_url):
    """Parse `html` and return every <a href> as {text, url}.

    `url` is `href` resolved against `base_url` (so relative links become
    absolute); `text` is the anchor's visible text with whitespace
    collapsed to single spaces. Anchors with no `href` attribute, or an
    empty/whitespace-only one, are skipped.

    Raises `ImportError` if `beautifulsoup4` isn't installed - imported
    lazily here so the rest of the script works without it.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href:
            continue
        text = " ".join(anchor.get_text(separator=" ").split())
        links.append({"text": text, "url": urljoin(base_url, href)})
    return links


def fetch_links(url, timeout=TIMEOUT_SECONDS):
    """GET `url` and return the links found in its HTML content.

    Returns a dict with url, final_url (after redirects), status_code,
    content_type, link_count, and links (a list of {text, url} dicts, in
    document order).

    Raises `requests.HTTPError` on a 4xx/5xx response, `ValueError` if the
    response's Content-Type isn't HTML, `ImportError` if
    `beautifulsoup4` isn't installed, and lets connection-level failures
    (DNS, timeout, refused connection, ...) propagate as
    requests.RequestException for the caller to handle.
    """
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "") or ""
    if "html" not in content_type.lower():
        raise ValueError(
            f"URL did not return HTML content (Content-Type: {content_type or 'unknown'})"
        )

    links = extract_links(response.text, response.url)
    return {
        "url": url,
        "final_url": response.url,
        "status_code": response.status_code,
        "content_type": content_type,
        "link_count": len(links),
        "links": links,
    }


def format_result(result):
    lines = [f"URL: {result['url']}"]
    if result["final_url"] != result["url"]:
        lines.append(f"Redirected to: {result['final_url']}")
    lines.append(f"Status: {result['status_code']}")
    lines.append(f"Links found: {result['link_count']}")
    lines.append("")
    for index, link in enumerate(result["links"], start=1):
        label = link["text"] or "(no text)"
        lines.append(f"{index}. {label}")
        lines.append(f"   {link['url']}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Retrieve a web page and extract all the links in its content."
    )
    parser.add_argument("url", help="URL to fetch, e.g. https://example.com")
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

    if not args.url.startswith(("http://", "https://")):
        die(f"URL must start with http:// or https://, got: {args.url}", args.json)

    if not args.json:
        print(f"Fetching: {args.url}\n")

    try:
        result = fetch_links(args.url, timeout=args.timeout)
    except ImportError:
        die("beautifulsoup4 is required (pip install beautifulsoup4)", args.json)
    except (requests.RequestException, ValueError) as exc:
        die(str(exc), args.json)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))


if __name__ == "__main__":
    main()
