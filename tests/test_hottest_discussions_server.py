"""Tests for app/hottest_discussions/hottest_discussions_server: page, limit parsing, discussions, HTTP handler, arg parsing."""

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


class TestRenderPage:
    def test_limit_options_mark_only_the_default(self):
        out = hds.render_limit_options()
        assert 'value="10" selected' in out
        assert out.count(" selected") == 1
        assert out.count("<option") == len(hds.LIMIT_OPTIONS) == 3

    def test_shell_starts_empty_and_calls_the_api(self):
        html = hds.render_page()
        assert "<!DOCTYPE html>" in html
        assert 'id="refresh-btn"' in html and 'id="limit-select"' in html
        assert "No discussions loaded yet" in html
        assert "/api/discussions?limit=" in html
        assert "__LIMIT_OPTIONS__" not in html
        # No JavaScript copy of the ranking: the page never calls HN itself.
        assert "firebaseio.com" not in html


class TestParseLimit:
    @pytest.mark.parametrize("value, expected", [("10", 10), ("25", 25), ("50", 50), (" 25 ", 25)])
    def test_accepts_options(self, value, expected):
        assert hds.parse_limit(value) == expected

    @pytest.mark.parametrize("value", ["", "abc", "0", "11", "100", "-10", None])
    def test_rejects_others(self, value):
        with pytest.raises(ValueError, match="limit must be one of 10, 25, 50"):
            hds.parse_limit(value)


class TestGetDiscussions:
    def test_runs_the_script_and_shapes_rows(self, monkeypatch):
        seen = []
        stories = [
            {"id": 1, "title": "One", "score": 50, "descendants": 4, "time": 0, "url": "https://a.example"},
            {"id": 2, "title": "Two", "score": 30, "time": 0},
        ]
        monkeypatch.setattr(hds.hn, "get_hottest_tech_discussions", lambda limit: seen.append(limit) or stories)
        out = hds.get_discussions(25)
        assert seen == [25]
        assert out["limit"] == 25
        assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d UTC", out["fetched_at"])
        assert out["discussions"] == [hds.hn.story_to_dict(1, stories[0]), hds.hn.story_to_dict(2, stories[1])]
        assert out["discussions"][1]["url"] == "https://news.ycombinator.com/item?id=2"
        json.dumps(out)  # must be serializable for the HTTP response


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
        monkeypatch.setattr(hds, "get_discussions", lambda limit: seen.append(limit) or {"limit": limit})
        h = _get("/api/discussions?limit=50")
        assert h.status == 200
        assert h.headers_out["Content-Type"].startswith("application/json")
        assert seen == [50]
        assert json.loads(h.wfile.getvalue()) == {"limit": 50}

    def test_missing_limit_defaults_to_10(self, monkeypatch):
        seen = []
        monkeypatch.setattr(hds, "get_discussions", lambda limit: seen.append(limit) or {})
        assert _get("/api/discussions").status == 200
        assert seen == [10]

    def test_invalid_limit_is_400(self, monkeypatch):
        monkeypatch.setattr(hds, "get_discussions", lambda limit: pytest.fail("should not fetch"))
        h = _get("/api/discussions?limit=7")
        assert h.status == 400
        assert "limit must be one of" in json.loads(h.wfile.getvalue())["error"]

    @pytest.mark.parametrize("exc", [requests.ConnectionError("down"), ValueError("bad json")])
    def test_fetch_error_is_502(self, monkeypatch, exc):
        def boom(limit):
            raise exc

        monkeypatch.setattr(hds, "get_discussions", boom)
        h = _get("/api/discussions?limit=10")
        assert h.status == 502
        assert json.loads(h.wfile.getvalue())["error"].startswith(
            "failed to fetch discussions from Hacker News:"
        )

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
