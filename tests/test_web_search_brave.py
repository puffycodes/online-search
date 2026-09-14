"""Tests for web_search_brave: markup stripping, dotenv loading, fetch pagination, and main()."""

import json
import os

import pytest
import requests

import web_search_brave as wsb
from helpers import FakeResponse


class TestStripMarkup:
    def test_removes_strong_tags(self):
        assert wsb.strip_markup("<strong>Python</strong> is great") == "Python is great"

    def test_unescapes_entities(self):
        assert wsb.strip_markup("Tom &amp; Jerry") == "Tom & Jerry"

    def test_plain_text_unchanged(self):
        assert wsb.strip_markup("plain text") == "plain text"


class TestLoadDotenv:
    def test_missing_file_is_silently_ignored(self, tmp_path):
        wsb.load_dotenv(path=str(tmp_path / "nope.env"))

    def test_populates_environ(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WSB_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("WSB_TEST_KEY=abc123\n# a comment\n\nBAD_LINE_NO_EQUALS\n")
        wsb.load_dotenv(path=str(env_file))
        assert os.environ["WSB_TEST_KEY"] == "abc123"

    def test_quoted_value_is_unquoted(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WSB_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text('WSB_TEST_KEY="quoted value"\n')
        wsb.load_dotenv(path=str(env_file))
        assert os.environ["WSB_TEST_KEY"] == "quoted value"

    def test_real_env_var_takes_precedence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WSB_TEST_KEY", "real")
        env_file = tmp_path / ".env"
        env_file.write_text("WSB_TEST_KEY=fromfile\n")
        wsb.load_dotenv(path=str(env_file))
        assert os.environ["WSB_TEST_KEY"] == "real"


class TestFetchResults:
    def test_single_page(self, monkeypatch):
        response = FakeResponse(
            json_data={"web": {"results": [{"title": "A"}, {"title": "B"}]}}
        )
        calls = []

        def fake_get(url, **kwargs):
            calls.append(kwargs)
            return response

        monkeypatch.setattr(wsb.requests, "get", fake_get)
        results = wsb.fetch_results("q", 2, "key")
        assert results == [{"title": "A"}, {"title": "B"}]
        assert len(calls) == 1
        assert calls[0]["params"]["count"] == 2
        assert calls[0]["params"]["offset"] == 0
        assert calls[0]["headers"]["X-Subscription-Token"] == "key"

    def test_paginates_when_page_is_full(self, monkeypatch):
        page1 = FakeResponse(
            json_data={"web": {"results": [{"title": str(i)} for i in range(20)]}}
        )
        page2 = FakeResponse(
            json_data={"web": {"results": [{"title": "20"}, {"title": "21"}]}}
        )
        responses = [page1, page2]
        monkeypatch.setattr(wsb.requests, "get", lambda url, **kw: responses.pop(0))

        results = wsb.fetch_results("q", 22, "key")
        assert len(results) == 22
        assert results[-1]["title"] == "21"

    def test_stops_when_fewer_results_than_requested(self, monkeypatch):
        response = FakeResponse(json_data={"web": {"results": [{"title": "A"}]}})
        monkeypatch.setattr(wsb.requests, "get", lambda url, **kw: response)
        results = wsb.fetch_results("q", 10, "key")
        assert results == [{"title": "A"}]

    def test_truncates_to_limit(self, monkeypatch):
        response = FakeResponse(
            json_data={"web": {"results": [{"title": str(i)} for i in range(5)]}}
        )
        monkeypatch.setattr(wsb.requests, "get", lambda url, **kw: response)
        results = wsb.fetch_results("q", 3, "key")
        assert len(results) == 3

    def test_raise_for_status_propagates(self, monkeypatch):
        response = FakeResponse(raise_for_status=requests.HTTPError("500"))
        monkeypatch.setattr(wsb.requests, "get", lambda url, **kw: response)
        with pytest.raises(requests.HTTPError):
            wsb.fetch_results("q", 1, "key")


class TestResultToDict:
    def test_strips_markup_and_joins_snippet_lines(self):
        item = {
            "title": "<strong>Py</strong>thon",
            "url": "http://x",
            "description": "A &amp; B\nsecond line",
        }
        row = wsb.result_to_dict(1, item)
        assert row == {
            "rank": 1,
            "title": "Python",
            "url": "http://x",
            "snippet": "A & B second line",
        }

    def test_missing_fields_use_defaults(self):
        row = wsb.result_to_dict(2, {})
        assert row["title"] == "(no title)"
        assert row["url"] == ""
        assert row["snippet"] == ""


class TestFormatResult:
    def test_formats_three_lines(self):
        row = {"rank": 1, "title": "T", "url": "U", "snippet": "S"}
        assert wsb.format_result(row) == "1. T\n   U\n   S"


class TestParseArgs:
    def test_defaults(self):
        args = wsb.parse_args(["python"])
        assert args.query == "python"
        assert args.limit == wsb.RESULTS_TO_SHOW
        assert args.json is False

    def test_flags(self):
        args = wsb.parse_args(["python", "--limit", "5", "--json"])
        assert args.limit == 5
        assert args.json is True

    def test_invalid_limit_rejected(self):
        with pytest.raises(SystemExit):
            wsb.parse_args(["python", "--limit", "0"])


class TestMain:
    def test_missing_api_key_exits_json(self, monkeypatch, capsys):
        monkeypatch.setattr(wsb, "load_dotenv", lambda: None)
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            wsb.main(["python", "--json"])
        assert exc.value.code == 1
        err = json.loads(capsys.readouterr().err)
        assert "BRAVE_API_KEY" in err["error"]

    def test_missing_api_key_exits_text(self, monkeypatch, capsys):
        monkeypatch.setattr(wsb, "load_dotenv", lambda: None)
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        with pytest.raises(SystemExit):
            wsb.main(["python"])
        assert "BRAVE_API_KEY" in capsys.readouterr().err

    def test_request_error_exits_json(self, monkeypatch, capsys):
        monkeypatch.setattr(wsb, "load_dotenv", lambda: None)
        monkeypatch.setenv("BRAVE_API_KEY", "key")

        def boom(*a, **k):
            raise requests.RequestException("network down")

        monkeypatch.setattr(wsb, "fetch_results", boom)
        with pytest.raises(SystemExit) as exc:
            wsb.main(["python", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "network down"}

    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(wsb, "load_dotenv", lambda: None)
        monkeypatch.setenv("BRAVE_API_KEY", "key")
        monkeypatch.setattr(
            wsb, "fetch_results",
            lambda q, l, k: [{"title": "A", "url": "u", "description": "d"}],
        )
        wsb.main(["python", "--json"])
        rows = json.loads(capsys.readouterr().out)
        assert rows == [{"rank": 1, "title": "A", "url": "u", "snippet": "d"}]

    def test_no_results(self, monkeypatch, capsys):
        monkeypatch.setattr(wsb, "load_dotenv", lambda: None)
        monkeypatch.setenv("BRAVE_API_KEY", "key")
        monkeypatch.setattr(wsb, "fetch_results", lambda q, l, k: [])
        wsb.main(["python"])
        assert "No results found." in capsys.readouterr().out

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(wsb, "load_dotenv", lambda: None)
        monkeypatch.setenv("BRAVE_API_KEY", "key")
        monkeypatch.setattr(
            wsb, "fetch_results",
            lambda q, l, k: [{"title": "A", "url": "u", "description": "d"}],
        )
        wsb.main(["python"])
        out = capsys.readouterr().out
        assert "Searching for: python" in out
        assert "1. A" in out
        assert "u" in out
