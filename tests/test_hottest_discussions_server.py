"""Tests for app/hottest_discussions/hottest_discussions_server: page, limit and source parsing, discussions, HTTP handler, arg parsing."""

import io
import json
import re
import sys
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "app" / "hottest_discussions"))

import hottest_discussions_server as hds  # noqa: E402

HN_STORY = {"id": 1, "title": "One", "score": 50, "descendants": 4, "time": 0, "url": "https://a.example"}
LOBSTERS_STORY = {"short_id": "abc", "title": "Lob", "score": 9, "comment_count": 2,
                  "created_at": "2026-10-18T12:00:00.000+00:00", "url": "",
                  "comments_url": "https://lobste.rs/s/abc/lob", "tags": ["rust"]}


def wire(monkeypatch, hn=(), lobsters=()):
    """Patch both sites' fetches inside the script, recording each site's limit."""
    seen = {}

    def fake_hn(limit):
        seen["hn"] = limit
        return list(hn)

    def fake_lobsters(limit, exclude_tags=()):
        seen["lobsters"] = limit
        return list(lobsters)

    monkeypatch.setattr(hds.hn, "get_hottest_tech_discussions", fake_hn)
    monkeypatch.setattr(hds.hn.lobsters, "fetch_hottest", fake_lobsters)
    return seen


class TestRenderPage:
    def test_limit_options_mark_only_the_default(self):
        out = hds.render_limit_options()
        assert 'value="10" selected' in out
        assert out.count(" selected") == 1
        assert out.count("<option") == len(hds.LIMIT_OPTIONS) == 3

    def test_source_options_default_to_hacker_news(self):
        out = hds.render_source_options()
        assert '<option value="hn" selected>Hacker News</option>' in out
        assert '<option value="lobsters">Lobsters</option>' in out
        assert '<option value="all">All Sources</option>' in out
        assert out.count(" selected") == 1
        assert out.index("Hacker News") < out.index("Lobsters") < out.index("All Sources")

    def test_shell_starts_empty_and_calls_the_api(self):
        html = hds.render_page()
        assert "<!DOCTYPE html>" in html
        assert 'id="refresh-btn"' in html and 'id="limit-select"' in html and 'id="source-select"' in html
        assert "per site" in html
        assert "No discussions loaded yet" in html
        assert "/api/discussions?limit=" in html and "&source=" in html
        assert "__LIMIT_OPTIONS__" not in html and "__SOURCE_OPTIONS__" not in html
        # Each site's link names it, and Lobsters rows show their tags.
        assert "discuss on HN" in html and "discuss on Lobsters" in html
        assert "Tags: " in html
        # No JavaScript copy of the ranking: the page never calls either site itself.
        assert "firebaseio.com" not in html and "lobste.rs" not in html


class TestParseLimit:
    @pytest.mark.parametrize("value, expected", [("10", 10), ("25", 25), ("50", 50), (" 25 ", 25)])
    def test_accepts_options(self, value, expected):
        assert hds.parse_limit(value) == expected

    @pytest.mark.parametrize("value", ["", "abc", "0", "11", "100", "-10", None])
    def test_rejects_others(self, value):
        with pytest.raises(ValueError, match="limit must be one of 10, 25, 50"):
            hds.parse_limit(value)


class TestParseSource:
    @pytest.mark.parametrize("value", ["hn", "lobsters", "all"])
    def test_accepts_options(self, value):
        assert hds.parse_source(value) == value

    @pytest.mark.parametrize("value", ["", "HN", "reddit", "hn,lobsters", None])
    def test_rejects_others(self, value):
        with pytest.raises(ValueError, match="source must be one of hn, lobsters, all"):
            hds.parse_source(value)


class TestGetDiscussions:
    def test_hacker_news_by_default(self, monkeypatch):
        seen = wire(monkeypatch, hn=[HN_STORY, {"id": 2, "title": "Two", "score": 30, "time": 0}])
        out = hds.get_discussions(25)
        assert seen == {"hn": 25}
        assert out["limit"] == 25 and out["source"] == "hn"
        assert out["sites"] == [{"id": "hn", "name": "Hacker News"}]
        assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d UTC", out["fetched_at"])
        assert out["discussions"][0] == hds.hn.story_to_dict(1, HN_STORY)
        assert out["discussions"][1]["url"] == "https://news.ycombinator.com/item?id=2"
        json.dumps(out)  # must be serializable for the HTTP response

    def test_lobsters_only(self, monkeypatch):
        seen = wire(monkeypatch, hn=[HN_STORY], lobsters=[LOBSTERS_STORY])
        out = hds.get_discussions(10, "lobsters")
        assert seen == {"lobsters": 10}
        assert out["sites"] == [{"id": "lobsters", "name": "Lobsters"}]
        row = out["discussions"][0]
        assert (row["source"], row["tags"], row["url"]) == ("lobsters", ["rust"], "https://lobste.rs/s/abc/lob")

    def test_all_sources_per_site_and_grouped(self, monkeypatch):
        seen = wire(monkeypatch, hn=[HN_STORY], lobsters=[LOBSTERS_STORY, dict(LOBSTERS_STORY, short_id="d")])
        out = hds.get_discussions(50, "all")
        assert seen == {"hn": 50, "lobsters": 50}
        assert [s["id"] for s in out["sites"]] == ["hn", "lobsters"]
        assert [(r["source"], r["rank"]) for r in out["discussions"]] == [("hn", 1), ("lobsters", 1), ("lobsters", 2)]

    def test_an_empty_site_still_gets_its_section(self, monkeypatch):
        wire(monkeypatch, hn=[HN_STORY])
        out = hds.get_discussions(10, "all")
        assert [s["id"] for s in out["sites"]] == ["hn", "lobsters"]
        assert [r["source"] for r in out["discussions"]] == ["hn"]

    @pytest.mark.parametrize("error", [requests.ConnectionError("down"), ValueError("down")])
    def test_a_failed_site_raises_naming_it(self, monkeypatch, error):
        wire(monkeypatch, hn=[HN_STORY])

        def boom(limit, exclude_tags=()):
            raise error

        monkeypatch.setattr(hds.hn.lobsters, "fetch_hottest", boom)
        with pytest.raises(hds.hn.SourceError, match="^Lobsters: down$"):
            hds.get_discussions(10, "all")


class _Handler(hds.HottestDiscussionsHandler):
    """Drives do_GET without a socket: captures status, headers, and body."""

    def __init__(self, path):
        self.path = path
        self.wfile = io.BytesIO()
        self.status = None
        self.headers_out = {}

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, key, value):
        self.headers_out[key] = value

    def end_headers(self):
        pass


def _get(path):
    handler = _Handler(path)
    handler.do_GET()
    return handler


class TestHandler:
    def test_serves_page(self):
        h = _get("/")
        assert h.status == 200
        assert h.headers_out["Content-Type"].startswith("text/html")
        assert 'id="discussions"' in h.wfile.getvalue().decode()

    def test_discussions_success(self, monkeypatch):
        seen = []
        monkeypatch.setattr(hds, "get_discussions",
                            lambda limit, source: seen.append((limit, source)) or {"limit": limit})
        h = _get("/api/discussions?limit=50&source=all")
        assert h.status == 200
        assert h.headers_out["Content-Type"].startswith("application/json")
        assert seen == [(50, "all")]
        assert json.loads(h.wfile.getvalue()) == {"limit": 50}

    def test_missing_params_default_to_10_from_hacker_news(self, monkeypatch):
        seen = []
        monkeypatch.setattr(hds, "get_discussions", lambda limit, source: seen.append((limit, source)) or {})
        assert _get("/api/discussions").status == 200
        assert seen == [(10, "hn")]

    @pytest.mark.parametrize("query, message", [
        ("limit=7", "limit must be one of"),
        ("limit=10&source=reddit", "source must be one of"),
    ])
    def test_invalid_params_are_400(self, monkeypatch, query, message):
        monkeypatch.setattr(hds, "get_discussions", lambda limit, source: pytest.fail("should not fetch"))
        h = _get("/api/discussions?" + query)
        assert h.status == 400
        assert message in json.loads(h.wfile.getvalue())["error"]

    @pytest.mark.parametrize("source, name", [("hn", "Hacker News"), ("lobsters", "Lobsters")])
    def test_fetch_error_is_502_naming_the_site(self, monkeypatch, source, name):
        def boom(limit, source_choice):
            raise hds.hn.SourceError(source, ValueError("bad json"))

        monkeypatch.setattr(hds, "get_discussions", boom)
        h = _get("/api/discussions?limit=10&source=all")
        assert h.status == 502
        assert json.loads(h.wfile.getvalue())["error"] == f"failed to fetch discussions from {name}: bad json"

    def test_unknown_path_is_404(self):
        assert _get("/nope").status == 404


class TestParseArgs:
    def test_defaults(self):
        args = hds.parse_args([])
        assert (args.host, args.port) == (hds.DEFAULT_HOST, hds.DEFAULT_PORT) == ("127.0.0.1", 8001)

    def test_overrides(self):
        args = hds.parse_args(["--host", "0.0.0.0", "--port", "9001"])
        assert (args.host, args.port) == ("0.0.0.0", 9001)

    def test_bad_port_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            hds.parse_args(["--port", "abc"])
        assert exc.value.code == 2
