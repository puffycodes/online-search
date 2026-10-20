#!/usr/bin/env python3
"""
Retrieve the raw content (HTML/text/JSON/etc.) of a web page at a given URL,
via a single HTTP GET request.

This is a straight content fetch, not a scraper: by default it does not
strip HTML tags, follow links, or render JavaScript - `content` is exactly
what the server sent back, decoded as text. Non-textual responses (images,
PDFs, other binary payloads) are rejected rather than returned as garbled
text. Pass --text to instead extract just the human-readable text of an
HTML page (via BeautifulSoup), with script/style content and markup
stripped out; it also reports the page's title, read from the same download
with url_metadata.py's extract_metadata() (the <title>, else og:title).

--respect-robots makes the fetch ask first: it reads the site's robots.txt
(robots.py) and refuses the page if a rule disallows it for this script, if
the site opts out of AI input (Content-Signal: ai-input=no), or if robots.txt
can't be read because of a server or connection error. A redirect to another
page is checked too, and its content discarded if that page is refused. Use
it whenever an agent, not the user, chose the URL; a refusal exits with
code 1 and an error starting "blocked".

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json

import requests

import robots
from cli_utils import die, positive_int, response_text, use_utf8_output, validate_url_scheme
from url_metadata import extract_metadata

TIMEOUT_SECONDS = 10
MAX_CHARS = 20000
USER_AGENT = "Mozilla/5.0 (compatible; online-search-url-content/1.0)"
# The product token matched against robots.txt User-agent groups.
ROBOTS_TOKEN = "online-search-url-content"

TEXTUAL_CONTENT_TYPE_MARKERS = ("text/", "json", "xml", "javascript")


def is_text_content_type(content_type):
    """Whether a Content-Type header value looks like it holds text.

    A missing header is treated as text - some servers omit it, and we'd
    rather try to decode the body than refuse it outright.
    """
    if not content_type:
        return True
    content_type = content_type.lower()
    return any(marker in content_type for marker in TEXTUAL_CONTENT_TYPE_MARKERS)


def extract_text(html):
    """Strip an HTML document down to its human-readable text via BeautifulSoup.

    Drops <script>/<style>/<noscript> content entirely (their text isn't
    meant to be read), then flattens what's left into a single run of text
    with all whitespace (including the newlines get_text() inserts between
    inline elements) collapsed to single spaces.

    Raises `ImportError` if `beautifulsoup4` isn't installed - imported
    lazily here so the rest of the script works without it.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


def page_title(html, base_url):
    """The page's <title>, falling back to its og:title; None if it has neither."""
    meta = extract_metadata(html, base_url)
    return meta["title"] or meta["open_graph"].get("title")


def fetch_content(url, timeout=TIMEOUT_SECONDS, max_chars=MAX_CHARS, as_text=False):
    """GET `url` and return its decoded body.

    Returns a dict with url, final_url (after redirects), status_code,
    content_type, title, length (full content length in characters, after
    extraction if `as_text`), truncated (bool), text_extracted (bool,
    echoes `as_text`), and content (the body, cut to `max_chars`).

    With `as_text=True`, the body is run through `extract_text()` before
    truncation, so `content` is plain text rather than raw HTML, and an HTML
    page's (or a page with no Content-Type) `title` comes from
    `page_title()`. Otherwise `title` is None.

    Raises `requests.HTTPError` on a 4xx/5xx response, `ValueError` if the
    response's Content-Type doesn't look textual, `ImportError` if
    `as_text` is set but `beautifulsoup4` isn't installed, and lets
    connection-level failures (DNS, timeout, refused connection, ...)
    propagate as `requests.RequestException` for the caller to handle.
    """
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type")
    if not is_text_content_type(content_type):
        raise ValueError(f"URL did not return text content (Content-Type: {content_type})")

    text = response_text(response)
    title = None
    if as_text:
        if not content_type or "html" in content_type.lower():
            title = page_title(text, response.url)
        text = extract_text(text)
    truncated = len(text) > max_chars
    return {
        "url": url,
        "final_url": response.url,
        "status_code": response.status_code,
        "content_type": content_type,
        "title": title,
        "length": len(text),
        "truncated": truncated,
        "text_extracted": as_text,
        "content": text[:max_chars],
    }


def format_result(result):
    lines = [f"URL: {result['url']}"]
    if result["final_url"] != result["url"]:
        lines.append(f"Redirected to: {result['final_url']}")
    lines.append(f"Status: {result['status_code']}")
    lines.append(f"Content-Type: {result['content_type']}")
    if result.get("title"):
        lines.append(f"Title: {result['title']}")
    length_line = f"Length: {result['length']} characters"
    if result["truncated"]:
        length_line += " (truncated)"
    lines.append(length_line)
    lines.append("")
    lines.append(result["content"])
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Retrieve the content of a web page at a given URL."
    )
    parser.add_argument("url", help="URL to fetch, e.g. https://example.com")
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=TIMEOUT_SECONDS,
        help=f"Request timeout in seconds (default: {TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--max-chars",
        type=positive_int,
        default=MAX_CHARS,
        help=f"Maximum characters of content to return (default: {MAX_CHARS})",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help=(
            "Extract just the human-readable text of an HTML page (via BeautifulSoup) "
            "instead of returning the raw markup. Requires beautifulsoup4."
        ),
    )
    parser.add_argument(
        "--respect-robots",
        action="store_true",
        help=(
            "Check the site's robots.txt first, and refuse the page if it is disallowed "
            "or the site opts out of AI input (Content-Signal: ai-input=no). Use when "
            "an agent, not the user, chose the URL."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def robots_refusal(url, timeout):
    """None if robots.txt lets this script fetch `url` for AI use, else why not."""
    return robots.check(url, USER_AGENT, ROBOTS_TOKEN, timeout=timeout)


def _same_page(a, b):
    """Whether two URLs name the same page, ignoring any #fragment."""
    return a.split("#", 1)[0] == b.split("#", 1)[0]


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    validate_url_scheme(args.url, args.json)

    if not args.json:
        print(f"Fetching: {args.url}\n")

    if args.respect_robots:
        refusal = robots_refusal(args.url, args.timeout)
        if refusal:
            die(f"blocked: {refusal}", args.json)

    try:
        result = fetch_content(
            args.url, timeout=args.timeout, max_chars=args.max_chars, as_text=args.text
        )
    except ImportError:
        die("beautifulsoup4 is required for --text (pip install beautifulsoup4)", args.json)
    except (requests.RequestException, ValueError) as exc:
        die(str(exc), args.json)

    if args.respect_robots and not _same_page(result["final_url"], args.url):
        # A redirect landed on another page (often another site), which has
        # its own rules; its content is discarded if that page is refused.
        refusal = robots_refusal(result["final_url"], args.timeout)
        if refusal:
            die(f"blocked after redirect to {result['final_url']}: {refusal}", args.json)
    result["robots_checked"] = args.respect_robots

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))


if __name__ == "__main__":
    main()
