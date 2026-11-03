"""Tests for url_feed: feed detection and discovery, RSS / RDF / Atom parsing,
dates, item selection, the report, robots handling and main()."""

import datetime as dt
import json

import pytest
import requests

import url_feed as uf
from helpers import FakeResponse

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>Example Blog</title><link>https://blog.example.com/</link>
  <item><title>Older post</title><link>https://blog.example.com/old</link>
    <pubDate>Mon, 19 Oct 2026 09:30:00 +0200</pubDate><dc:creator>Ann</dc:creator>
    <description>&lt;p&gt;First &lt;b&gt;bold&lt;/b&gt; paragraph.&lt;/p&gt;&lt;p&gt;Second.&lt;/p&gt;</description></item>
  <item><title>Newest post</title><link>https://blog.example.com/new</link>
    <pubDate>Tue, 20 Oct 2026 10:00:00 GMT</pubDate>
    <content:encoded><![CDATA[<p>Full text</p>]]></content:encoded></item>
  <item><title>Undated note</title><link>https://blog.example.com/note</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Releases</title>
  <link rel="self" href="https://example.org/releases.atom"/>
  <link href="https://example.org/releases"/>
  <entry><title>v2.0</title>
    <link rel="alternate" href="https://example.org/v2"/>
    <updated>2026-10-13T15:05:54Z</updated><author><name>Bot</name></author>
    <content type="html">&lt;h2&gt;Changes&lt;/h2&gt; lots</content></entry>
  <entry><title>v1.9</title><link href="https://example.org/v1.9"/>
    <published>2026-10-01T08:00:00+08:00</published><updated>2026-10-05T00:00:00Z</updated>
    <summary>Fixes</summary></entry>
</feed>"""

RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel><title>Old School</title><link>https://old.example/</link></channel>
  <item><title>An item</title><link>https://old.example/1</link>
    <dc:date>2026-10-20T12:00:00Z</dc:date><description>Text</description></item>
</rdf:RDF>"""

PAGE = b"""<html><head><title>Blog</title>
<link rel="stylesheet" href="/style.css">
<link rel="alternate" type="application/rss+xml" title="RSS" href="/feed.xml">
<link rel="alternate" type="application/atom+xml" href="/atom.xml">
</head><body>Hi</body></html>"""


def _response(body, content_type, url):
    response = FakeResponse(status_code=200, url=url)
    response.content = body
    response.headers = {"Content-Type": content_type}
    return response


class TestLooksLikeFeed:
    @pytest.mark.parametrize("content_type, body, expected", [
        ("application/rss+xml", b"", True),
        ("application/atom+xml; charset=utf-8", b"", True),
        ("text/xml", b"", True),
        ("application/xml", b"", True),
        ("text/html; charset=utf-8", b"<?xml version='1.0'?><rss/>", False),
        ("application/xhtml+xml", b"<html/>", False),
        ("text/plain", b"  <?xml version='1.0'?>", True),
        ("", b"<rss version='2.0'>", True),
        ("", b"<feed xmlns='x'>", True),
        ("application/octet-stream", b"hello", False),
    ])
    def test_matrix(self, content_type, body, expected):
        assert uf.looks_like_feed(content_type, body) is expected


class TestDiscoverFeed:
    def test_first_rss_or_atom_link_resolved(self):
        assert uf.discover_feed(PAGE, "https://blog.example.com/posts/") == "https://blog.example.com/feed.xml"

    def test_atom_only(self):
        page = b'<link rel="alternate" type="application/atom+xml" href="https://x.org/a.atom">'
        assert uf.discover_feed(page, "https://x.org/") == "https://x.org/a.atom"

    def test_none(self):
        assert uf.discover_feed(b'<link rel="alternate" hreflang="fr" href="/fr">', "https://x.org/") is None


class TestParseDate:
    @pytest.mark.parametrize("value, expected", [
        ("Mon, 19 Oct 2026 09:30:00 +0200", "2026-10-19T07:30:00Z"),
        ("Tue, 20 Oct 2026 10:00:00 GMT", "2026-10-20T10:00:00Z"),
        ("2026-10-13T15:05:54Z", "2026-10-13T15:05:54Z"),
        ("2026-10-01T08:00:00+08:00", "2026-10-01T00:00:00Z"),
        ("2026-10-01T08:00:00", "2026-10-01T08:00:00Z"),
        ("2026-10-01", "2026-10-01T00:00:00Z"),
        ("yesterday-ish", None),
        ("", None),
        (None, None),
    ])
    def test_matrix(self, value, expected):
        assert uf.parse_date(value) == expected


class TestParseFeed:
    def test_rss(self):
        feed = uf.parse_feed(RSS)
        assert (feed["format"], feed["title"], feed["site_url"]) == ("rss", "Example Blog", "https://blog.example.com/")
        old, new, note = feed["items"]
        assert old == {"title": "Older post", "link": "https://blog.example.com/old",
                       "published": "2026-10-19T07:30:00Z", "author": "Ann",
                       "summary": "First bold paragraph.\n\nSecond."}
        assert new["summary"] == "Full text" and new["author"] is None
        assert note["published"] is None and note["summary"] is None

    def test_atom(self):
        feed = uf.parse_feed(ATOM)
        assert (feed["format"], feed["title"], feed["site_url"]) == ("atom", "Releases", "https://example.org/releases")
        v2, v19 = feed["items"]
        assert v2["link"] == "https://example.org/v2" and v2["author"] == "Bot"
        assert v2["published"] == "2026-10-13T15:05:54Z" and v2["summary"] == "Changes lots"
        assert v19["published"] == "2026-10-01T00:00:00Z"  # published wins over updated
        assert v19["link"] == "https://example.org/v1.9" and v19["summary"] == "Fixes"

    def test_rdf(self):
        feed = uf.parse_feed(RDF)
        assert (feed["format"], feed["title"]) == ("rdf", "Old School")
        assert feed["items"][0]["published"] == "2026-10-20T12:00:00Z"

    def test_summary_cut(self):
        feed = uf.parse_feed(RSS, max_chars=10)
        assert feed["items"][0]["summary"] == "First bold..."

    def test_not_a_feed(self):
        with pytest.raises(uf.NotAFeed, match="<html> root"):
            uf.parse_feed(b"<html><body/></html>")

    def test_malformed(self):
        with pytest.raises(ValueError, match="malformed XML"):
            uf.parse_feed(b"<rss><channel>")

    def test_entity_expansion_refused(self):
        bomb = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>
<rss><channel><title>&lol2;</title></channel></rss>"""
        with pytest.raises(ValueError, match="refused unsafe XML"):
            uf.parse_feed(bomb)


class TestSelectItems:
    ITEMS = [{"published": "2026-10-19T07:30:00Z", "n": 1}, {"published": None, "n": 2},
             {"published": "2026-10-20T10:00:00Z", "n": 3}, {"published": None, "n": 4}]

    def test_newest_first_undated_last(self):
        items, skipped = uf.select_items(self.ITEMS, 10)
        assert [i["n"] for i in items] == [3, 1, 2, 4] and skipped == 0

    def test_limit(self):
        assert [i["n"] for i in uf.select_items(self.ITEMS, 2)[0]] == [3, 1]

    def test_since_drops_older_and_undated(self):
        items, skipped = uf.select_items(self.ITEMS, 10, since=dt.date(2026, 10, 20))
        assert [i["n"] for i in items] == [3] and skipped == 2


@pytest.fixture
def web(monkeypatch):
    """requests.get faked by URL; returns the list of requested URLs."""
    pages = {
        "https://blog.example.com/": (PAGE, "text/html; charset=utf-8"),
        "https://blog.example.com/feed.xml": (RSS, "application/rss+xml"),
        "https://example.org/releases.atom": (ATOM, "application/atom+xml"),
        "https://example.com/": (b"<html><head></head></html>", "text/html"),
    }
    calls = []

    def fake_get(url, headers, timeout, allow_redirects):
        calls.append((url, headers["User-Agent"]))
        if url not in pages:
            raise requests.HTTPError("404 Client Error: Not Found")
        body, content_type = pages[url]
        return _response(body, content_type, url)

    monkeypatch.setattr(uf.requests, "get", fake_get)
    return calls


class TestReadFeed:
    def test_direct_feed(self, web):
        result = uf.read_feed("https://example.org/releases.atom", limit=1)
        assert result["discovered"] is False and result["format"] == "atom"
        assert result["item_count"] == 2 and [i["title"] for i in result["items"]] == ["v2.0"]
        assert web == [("https://example.org/releases.atom", uf.USER_AGENT)]

    def test_discovered_from_page(self, web):
        result = uf.read_feed("https://blog.example.com/")
        assert result["discovered"] is True and result["feed_url"] == "https://blog.example.com/feed.xml"
        assert [i["title"] for i in result["items"]] == ["Newest post", "Older post", "Undated note"]

    def test_robots_check_on_page_and_feed(self, web):
        checked = []
        uf.read_feed("https://blog.example.com/", robots_check=checked.append)
        assert checked == ["https://blog.example.com/", "https://blog.example.com/feed.xml"]

    def test_page_without_feed(self, web):
        with pytest.raises(uf.NotAFeed, match="doesn't link to one"):
            uf.read_feed("https://example.com/")

    def test_too_large(self, web, monkeypatch):
        monkeypatch.setattr(uf, "MAX_BYTES", 10)
        with pytest.raises(ValueError, match="larger than"):
            uf.read_feed("https://example.org/releases.atom")


class TestFormatResult:
    def test_report(self, web):
        result = uf.read_feed("https://blog.example.com/", limit=2)
        result.update(ai_input_warning=None, robots_disallow_note="robots asks not to fetch /feed.xml")
        out = uf.format_result(result)
        assert out.startswith("Feed: Example Blog (RSS)\n  https://blog.example.com/feed.xml\n  found on https://blog.example.com/")
        assert "Note: robots asks not to fetch /feed.xml" in out
        assert "Showing 2 of 3 item(s), newest first" in out
        assert "1. Newest post\n   2026-10-20 10:00:00 UTC\n   https://blog.example.com/new\n   Full text" in out
        assert "2026-10-19 07:30:00 UTC - Ann" in out


class TestMain:
    def test_json(self, web, capsys):
        uf.main(["https://example.org/releases.atom", "--json"])
        result = json.loads(capsys.readouterr().out)
        assert result["robots_checked"] is False and result["ai_input_warning"] is None
        assert len(result["items"]) == 2

    def test_text_progress_line(self, web, capsys):
        uf.main(["https://example.org/releases.atom"])
        assert capsys.readouterr().out.startswith("Reading the feed for: https://example.org/releases.atom")

    def test_respect_robots_refuses(self, web, monkeypatch, capsys):
        monkeypatch.setattr(uf.robots, "check", lambda url, ua, token, timeout: "x.org's robots.txt disallows /")
        with pytest.raises(SystemExit) as exc:
            uf.main(["https://example.org/releases.atom", "--respect-robots", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err)["error"] == "blocked: x.org's robots.txt disallows /"

    def test_warn_robots_notes(self, web, monkeypatch, capsys):
        reviewed = []

        def fake_review(url, ua, token, timeout):
            reviewed.append((url, token))
            return {"ai_input": "opts out of AI input", "disallowed": None}

        monkeypatch.setattr(uf.robots, "review", fake_review)
        uf.main(["https://blog.example.com/", "--warn-robots", "--json"])
        result = json.loads(capsys.readouterr().out)
        assert reviewed == [("https://blog.example.com/feed.xml", uf.ROBOTS_TOKEN)]
        assert result["robots_checked"] is True and result["ai_input_warning"] == "opts out of AI input"

    def test_not_a_feed_exits_1(self, web, capsys):
        with pytest.raises(SystemExit) as exc:
            uf.main(["https://example.com/", "--json"])
        assert exc.value.code == 1
        assert "doesn't link to one" in json.loads(capsys.readouterr().err)["error"]

    def test_http_error_exits_1(self, web, capsys):
        with pytest.raises(SystemExit) as exc:
            uf.main(["https://nowhere.example/feed"])
        assert exc.value.code == 1 and "404" in capsys.readouterr().err

    @pytest.mark.parametrize("argv", [
        ["https://x.org/", "--limit", "0"],
        ["https://x.org/", "--since", "20/10/2026"],
        ["https://x.org/", "--respect-robots", "--warn-robots"],
    ])
    def test_bad_options_exit_2(self, argv):
        with pytest.raises(SystemExit) as exc:
            uf.main(argv)
        assert exc.value.code == 2

    def test_bad_scheme_exits_1(self, capsys):
        with pytest.raises(SystemExit) as exc:
            uf.main(["example.org/feed", "--json"])
        assert exc.value.code == 1
