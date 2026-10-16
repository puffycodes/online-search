#!/usr/bin/env python3
"""
Retrieve a web page at a given URL and extract its metadata: the
``<title>``, the meta description, the canonical URL, and the OpenGraph
(``og:*``) and Twitter-card (``twitter:*``) tags that sites use for link
previews.

Parses the page via BeautifulSoup. The canonical URL and the ``og:url`` /
``og:image`` / ``twitter:image`` values are resolved against the page's
final URL (after redirects), so a relative value comes back absolute. A
tag that appears more than once keeps its first value. Anything the page
doesn't declare is null (or an empty object for the two tag groups).

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json
from urllib.parse import urljoin

import requests

from cli_utils import die, positive_int, response_text, use_utf8_output, validate_url_scheme

TIMEOUT_SECONDS = 10
USER_AGENT = "Mozilla/5.0 (compatible; online-search-url-metadata/1.0)"

# Tag-group prefixes and the keys (without prefix) whose values are URLs.
TAG_GROUPS = {"open_graph": "og:", "twitter": "twitter:"}
URL_KEYS = {"url", "image", "image:url", "image:secure_url"}


def _clean(text):
    """Collapse whitespace; None for a missing or blank value."""
    text = " ".join((text or "").split())
    return text or None


def extract_metadata(html, base_url):
    """Parse `html` and return {title, description, canonical, open_graph, twitter}.

    `open_graph` and `twitter` map each tag's name without its prefix
    (``og:title`` -> ``title``) to its content. Meta names are matched
    case-insensitively, from either the ``property`` or the ``name``
    attribute, since sites use both.

    Raises `ImportError` if `beautifulsoup4` isn't installed - imported
    lazily here so the rest of the script works without it.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # Prefer the <head> title: an inline <svg> can carry its own <title>.
    title_tag = (soup.head and soup.head.find("title")) or soup.find("title")
    title = _clean(title_tag.get_text()) if title_tag else None

    description = None
    groups = {group: {} for group in TAG_GROUPS}
    for meta in soup.find_all("meta"):
        key = (meta.get("property") or meta.get("name") or "").strip().lower()
        content = _clean(meta.get("content"))
        if not key or content is None:
            continue
        if key == "description":
            description = description or content
            continue
        for group, prefix in TAG_GROUPS.items():
            if key.startswith(prefix):
                name = key[len(prefix):]
                if name in URL_KEYS:
                    content = urljoin(base_url, content)
                groups[group].setdefault(name, content)

    canonical = None
    for link in soup.find_all("link", href=True):
        rel = link.get("rel") or []
        if isinstance(rel, str):
            rel = rel.split()
        if "canonical" in (r.lower() for r in rel) and link["href"].strip():
            canonical = urljoin(base_url, link["href"].strip())
            break

    return {"title": title, "description": description, "canonical": canonical, **groups}


def fetch_metadata(url, timeout=TIMEOUT_SECONDS):
    """GET `url` and return the metadata found in its HTML content.

    Returns a dict with url, final_url (after redirects), status_code,
    content_type, and the fields of `extract_metadata()`.

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

    return {
        "url": url,
        "final_url": response.url,
        "status_code": response.status_code,
        "content_type": content_type,
        **extract_metadata(response_text(response), response.url),
    }


def format_result(result):
    lines = [f"URL: {result['url']}"]
    if result["final_url"] != result["url"]:
        lines.append(f"Redirected to: {result['final_url']}")
    lines.append(f"Status: {result['status_code']}")
    lines.append("")
    lines.append(f"Title:       {result['title'] or '-'}")
    lines.append(f"Description: {result['description'] or '-'}")
    lines.append(f"Canonical:   {result['canonical'] or '-'}")
    for group, label in (("open_graph", "OpenGraph"), ("twitter", "Twitter card")):
        lines.append("")
        tags = result[group]
        if not tags:
            lines.append(f"{label}: none")
            continue
        lines.append(f"{label}:")
        width = max(len(name) for name in tags)
        for name, value in tags.items():
            lines.append(f"  {name:<{width}}  {value}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Retrieve a web page and extract its title, description, "
                    "canonical URL, and OpenGraph / Twitter-card tags."
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
    use_utf8_output()
    args = parse_args(argv)

    validate_url_scheme(args.url, args.json)

    if not args.json:
        print(f"Fetching: {args.url}\n")

    try:
        result = fetch_metadata(args.url, timeout=args.timeout)
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
