#!/usr/bin/env python3
"""
Read the latest items from a site's RSS or Atom feed.

Give it either a feed's own URL or a web page: for a page, the feed is found
through the page's <link rel="alternate" type="application/rss+xml"> (or
atom+xml) tag, the way feed readers do. RSS 2.0, RSS 1.0 (RDF) and Atom are
parsed into the same item shape - title, link, published date, author and a
plain-text summary - and returned newest first.

Feeds are untrusted XML, so they are parsed with defusedxml, which refuses
entity-expansion and external-entity tricks. HTML in summaries is turned into
plain text with hn.clean_text(). Dates in the common RSS (RFC 822) and Atom
(ISO 8601) forms become UTC ISO timestamps; an unreadable date is left out
rather than guessed.

--respect-robots and --warn-robots work as in url_content.py: refuse a page
or feed whose robots.txt disallows this script or opts out of AI input (for
feeds an agent chose itself), or fetch regardless and report what robots.txt
asks (for feeds the user chose). Both the page and a discovered feed are
checked.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import datetime as dt
import email.utils
import json
from urllib.parse import urljoin

import requests

import robots
from cli_utils import die, positive_int, use_utf8_output, validate_url_scheme
from hn import clean_text

TIMEOUT_SECONDS = 10
DEFAULT_LIMIT = 10
SUMMARY_CHARS = 300
MAX_BYTES = 5 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; online-search-url-feed/1.0)"
# The product token matched against robots.txt User-agent groups.
ROBOTS_TOKEN = "online-search-url-feed"
FEED_TYPES = ("application/rss+xml", "application/atom+xml")

ATOM = "{http://www.w3.org/2005/Atom}"
RSS1 = "{http://purl.org/rss/1.0/}"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"


class NotAFeed(ValueError):
    """The response was neither a feed nor a page that links to one."""


def fetch(url, timeout):
    """GET ``url``; return (final_url, content_type, body bytes).

    Raises requests.RequestException for a network error or a 4xx/5xx
    status, and ValueError for a body over MAX_BYTES.
    """
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout,
                            allow_redirects=True)
    response.raise_for_status()
    body = response.content
    if len(body) > MAX_BYTES:
        raise ValueError(f"response is larger than {MAX_BYTES // (1024 * 1024)} MB")
    return response.url, (response.headers.get("Content-Type") or "").lower(), body


def looks_like_feed(content_type, body):
    """Whether a response is XML (a feed) rather than an HTML page: by its
    Content-Type (HTML and XHTML are pages; RSS, Atom and other XML types
    are feeds), else by how the body starts."""
    base = content_type.split(";")[0].strip()
    if "html" in base:
        return False
    if base.endswith("xml") or "rss" in base or "atom" in base:
        return True
    head = body[:500].lstrip().lower()
    return head.startswith(b"<?xml") or head.startswith(b"<rss") or head.startswith(b"<feed")


def discover_feed(html, base_url):
    """The first feed advertised by an HTML page's <link rel="alternate"
    type="application/rss+xml|atom+xml" href="...">, as an absolute URL, or
    None. Raises ImportError if beautifulsoup4 isn't installed."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("link", href=True):
        rel = [r.lower() for r in (link.get("rel") or [])]
        kind = (link.get("type") or "").lower().split(";")[0].strip()
        if "alternate" in rel and kind in FEED_TYPES:
            return urljoin(base_url, link["href"].strip())
    return None


def parse_date(value):
    """An RFC 822 (RSS) or ISO 8601 (Atom, dc:date) date as a UTC
    "YYYY-MM-DDTHH:MM:SSZ" string, or None if it can't be read. A date
    without a time zone is taken as UTC."""
    if not value:
        return None
    value = value.strip()
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(element, *paths):
    """The stripped text of the first of ``paths`` under ``element`` that has some."""
    for path in paths:
        found = element.find(path)
        if found is not None and (found.text or "").strip():
            return found.text.strip()
    return None


def _item(title, link, published, author, summary, max_chars):
    return {
        "title": clean_text(title, 0) if title else None,
        "link": link,
        "published": parse_date(published),
        "author": author,
        "summary": clean_text(summary, max_chars),
    }


def _atom_link(element):
    """An Atom element's alternate link (rel="alternate" or no rel)."""
    for link in element.findall(f"{ATOM}link"):
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return link.get("href")
    return None


def parse_feed(body, max_chars=SUMMARY_CHARS):
    """Parse RSS 2.0, RSS 1.0 (RDF) or Atom bytes.

    Returns {format, title, site_url, items: [{title, link, published,
    author, summary}]} in the feed's own order. Raises NotAFeed for XML that
    isn't one of those, ValueError for malformed or unsafe XML, and
    ImportError if defusedxml isn't installed.
    """
    from defusedxml import ElementTree
    from defusedxml.common import DefusedXmlException

    try:
        root = ElementTree.fromstring(body)
    except DefusedXmlException as exc:
        raise ValueError(f"refused unsafe XML ({type(exc).__name__})") from None
    except ElementTree.ParseError as exc:
        raise ValueError(f"malformed XML: {exc}") from None

    if root.tag == f"{ATOM}feed":
        items = [
            _item(_text(entry, f"{ATOM}title"), _atom_link(entry),
                  _text(entry, f"{ATOM}published", f"{ATOM}updated"),
                  _text(entry, f"{ATOM}author/{ATOM}name"),
                  _text(entry, f"{ATOM}summary", f"{ATOM}content"), max_chars)
            for entry in root.findall(f"{ATOM}entry")
        ]
        return {"format": "atom", "title": _text(root, f"{ATOM}title"),
                "site_url": _atom_link(root), "items": items}

    if root.tag == "rss":
        channel = root.find("channel")
        if channel is None:
            raise NotAFeed("an <rss> document without a <channel>")
        items = [
            _item(_text(item, "title"), _text(item, "link"),
                  _text(item, "pubDate", f"{DC}date"),
                  _text(item, f"{DC}creator", "author"),
                  _text(item, "description", f"{CONTENT}encoded"), max_chars)
            for item in channel.findall("item")
        ]
        return {"format": "rss", "title": _text(channel, "title"),
                "site_url": _text(channel, "link"), "items": items}

    if root.tag == f"{RDF}RDF":
        channel = root.find(f"{RSS1}channel")
        items = [
            _item(_text(item, f"{RSS1}title"), _text(item, f"{RSS1}link"),
                  _text(item, f"{DC}date"), _text(item, f"{DC}creator"),
                  _text(item, f"{RSS1}description", f"{CONTENT}encoded"), max_chars)
            for item in root.findall(f"{RSS1}item")
        ]
        return {"format": "rdf",
                "title": _text(channel, f"{RSS1}title") if channel is not None else None,
                "site_url": _text(channel, f"{RSS1}link") if channel is not None else None,
                "items": items}

    raise NotAFeed(f"XML with a <{root.tag.split('}')[-1]}> root is not an RSS or Atom feed")


def select_items(items, limit, since=None):
    """Newest first (undated items after dated ones, in feed order), only
    those published on or after ``since`` (a date) when given, at most
    ``limit``. Returns (items, undated_skipped)."""
    dated = sorted((i for i in items if i["published"]), key=lambda i: i["published"], reverse=True)
    undated = [i for i in items if not i["published"]]
    skipped = 0
    if since is not None:
        cutoff = since.isoformat()
        dated = [i for i in dated if i["published"][:10] >= cutoff]
        skipped, undated = len(undated), []
    return (dated + undated)[:limit], skipped


def read_feed(url, limit=DEFAULT_LIMIT, since=None, max_chars=SUMMARY_CHARS,
              timeout=TIMEOUT_SECONDS, robots_check=None):
    """Fetch ``url`` (a feed, or a page that links to one) and return the
    result dict. ``robots_check(url)``, when given, is called on the page and
    on a discovered feed and may raise to refuse it."""
    if robots_check:
        robots_check(url)
    final_url, content_type, body = fetch(url, timeout)
    discovered = False
    if not looks_like_feed(content_type, body):
        feed_url = discover_feed(body, final_url)
        if feed_url is None:
            raise NotAFeed("the page is not a feed and doesn't link to one")
        if robots_check:
            robots_check(feed_url)
        final_url, content_type, body = fetch(feed_url, timeout)
        discovered = True
    feed = parse_feed(body, max_chars=max_chars)
    items, undated_skipped = select_items(feed["items"], limit, since)
    return {
        "url": url,
        "feed_url": final_url,
        "discovered": discovered,
        "format": feed["format"],
        "title": feed["title"],
        "site_url": feed["site_url"],
        "item_count": len(feed["items"]),
        "undated_skipped": undated_skipped,
        "items": items,
    }


def format_result(result):
    lines = [f"Feed: {result['title'] or '(untitled)'} ({result['format'].upper()})",
             f"  {result['feed_url']}"]
    if result["discovered"]:
        lines.append(f"  found on {result['url']}")
    for key in ("ai_input_warning", "robots_disallow_note"):
        if result.get(key):
            lines.append(f"Note: {result[key]}")
    shown = len(result["items"])
    lines.append(f"\nShowing {shown} of {result['item_count']} item(s), newest first")
    if result["undated_skipped"]:
        lines.append(f"({result['undated_skipped']} undated item(s) left out by --since)")
    for index, item in enumerate(result["items"], start=1):
        when = item["published"].replace("T", " ").replace("Z", " UTC") if item["published"] else "undated"
        lines += ["", f"{index}. {item['title'] or '(no title)'}", f"   {when}"
                  + (f" - {item['author']}" if item["author"] else "")]
        if item["link"]:
            lines.append(f"   {item['link']}")
        if item["summary"]:
            lines.append(f"   {item['summary']}")
    return "\n".join(lines)


def _date(value):
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a date as YYYY-MM-DD, got {value!r}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Read the latest items from a site's RSS or Atom feed."
    )
    parser.add_argument("url", help="A feed URL, or a page that links to its feed")
    parser.add_argument("--limit", type=positive_int, default=DEFAULT_LIMIT,
                        help=f"Most items to show (default: {DEFAULT_LIMIT})")
    parser.add_argument("--since", type=_date,
                        help="Only items published on or after this date, YYYY-MM-DD")
    parser.add_argument("--max-chars", type=positive_int, default=SUMMARY_CHARS,
                        help=f"Longest summary per item, in characters (default: {SUMMARY_CHARS})")
    parser.add_argument("--timeout", type=positive_int, default=TIMEOUT_SECONDS,
                        help=f"Request timeout in seconds (default: {TIMEOUT_SECONDS})")
    robots_mode = parser.add_mutually_exclusive_group()
    robots_mode.add_argument(
        "--respect-robots",
        action="store_true",
        help="Check robots.txt first (for the page and a discovered feed) and refuse one "
             "that is disallowed or opts out of AI input. Use when an agent chose the URL.",
    )
    robots_mode.add_argument(
        "--warn-robots",
        action="store_true",
        help="Fetch regardless, but report in ai_input_warning / robots_disallow_note what "
             "the feed's robots.txt asks. Use when the user chose the URL.",
    )
    parser.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON on stdout instead of a human-readable report.")
    return parser.parse_args(argv)


class RobotsRefusal(Exception):
    pass


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    validate_url_scheme(args.url, args.json)

    if not args.json:
        print(f"Reading the feed for: {args.url}\n")

    def refuse_if_blocked(url):
        reason = robots.check(url, USER_AGENT, ROBOTS_TOKEN, timeout=args.timeout)
        if reason:
            raise RobotsRefusal(f"blocked: {reason}")

    try:
        result = read_feed(
            args.url, limit=args.limit, since=args.since, max_chars=args.max_chars,
            timeout=args.timeout, robots_check=refuse_if_blocked if args.respect_robots else None,
        )
    except RobotsRefusal as exc:
        die(str(exc), args.json)
    except ImportError as exc:
        die(f"{exc.name or 'a dependency'} is required (pip install defusedxml beautifulsoup4)", args.json)
    except (requests.RequestException, ValueError) as exc:
        die(str(exc), args.json)

    result["robots_checked"] = args.respect_robots or args.warn_robots
    notes = (robots.review(result["feed_url"], USER_AGENT, ROBOTS_TOKEN, timeout=args.timeout)
             if args.warn_robots else {"ai_input": None, "disallowed": None})
    result["ai_input_warning"] = notes["ai_input"]
    result["robots_disallow_note"] = notes["disallowed"]

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_result(result))


if __name__ == "__main__":
    main()
