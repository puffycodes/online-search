"""Tests for web_search_exa: dotenv loading, fetch capping, and main()."""

import json
import os

import pytest
import requests

import web_search_exa as wse
from helpers import FakeResponse


class TestLoadDotenv:
    def test_missing_file_is_silently_ignored(self, tmp_path):
        wse.load_dotenv(path=str(tmp_path / "nope.env"))

    def test_populates_environ(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WSE_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("WSE_TEST_KEY=abc123\n# a comment\n\nBAD_LINE_NO_EQUALS\n")
        wse.load_dotenv(path=str(env_file))
        assert os.environ["WSE_TEST_KEY"] == "abc123"

    def test_quoted_value_is_unquoted(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WSE_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text('WSE_TEST_KEY="quoted value"\n')
        wse.load_dotenv(path=str(env_file))
        assert os.environ["WSE_TEST_KEY"] == "quoted value"

    def test_real_env_var_takes_precedence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WSE_TEST_KEY", "real")
        env_file = tmp_path / ".env"
        env_file.write_text("WSE_TEST_KEY=fromfile\n")
        wse.load_dotenv(path=str(env_file))
        assert os.environ["WSE_TEST_KEY"] == "real"


class TestFetchResults:
    def test_single_request(self, monkeypatch):
        response = FakeResponse(
            json_data={"results": [{"title": "A"}, {"title": "B"}]}
        )
        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs)
            return response

        monkeypatch.setattr(wse.requests, "post", fake_post)
        results = wse.fetch_results("q", 2, "key")
        assert results == [{"title": "A"}, {"title": "B"}]
        assert len(calls) == 1
        assert calls[0]["json"]["numResults"] == 2
        assert calls[0]["json"]["query"] == "q"
        assert calls[0]["headers"]["x-api-key"] == "key"
        assert calls[0]["json"]["contents"]["text"]["maxCharacters"] == wse.SNIPPET_MAX_CHARACTERS

    def test_caps_num_results_at_ceiling(self, monkeypatch):
        response = FakeResponse(json_data={"results": []})
        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs)
            return response

        monkeypatch.setattr(wse.requests, "post", fake_post)
        wse.fetch_results("q", wse.MAX_RESULTS_PER_REQUEST + 50, "key")
        assert calls[0]["json"]["numResults"] == wse.MAX_RESULTS_PER_REQUEST

    def test_truncates_to_limit(self, monkeypatch):
        response = FakeResponse(
            json_data={"results": [{"title": str(i)} for i in range(5)]}
        )
        monkeypatch.setattr(wse.requests, "post", lambda url, **kw: response)
        results = wse.fetch_results("q", 3, "key")
        assert len(results) == 3

    def test_raise_for_status_propagates(self, monkeypatch):
        response = FakeResponse(raise_for_status=requests.HTTPError("401"))
        monkeypatch.setattr(wse.requests, "post", lambda url, **kw: response)
        with pytest.raises(requests.HTTPError):
            wse.fetch_results("q", 1, "key")

    def test_missing_results_key_returns_empty(self, monkeypatch):
        response = FakeResponse(json_data={})
        monkeypatch.setattr(wse.requests, "post", lambda url, **kw: response)
        assert wse.fetch_results("q", 5, "key") == []


class TestResultToDict:
    def test_maps_text_and_joins_snippet_lines(self):
        item = {
            "title": "Python",
            "url": "http://x",
            "text": "first line\nsecond line",
        }
        row = wse.result_to_dict(1, item)
        assert row == {
            "rank": 1,
            "title": "Python",
            "url": "http://x",
            "snippet": "first line second line",
        }

    def test_missing_fields_use_defaults(self):
        row = wse.result_to_dict(2, {})
        assert row["title"] == "(no title)"
        assert row["url"] == ""
        assert row["snippet"] == ""

    def test_null_text_field_becomes_empty_snippet(self):
        row = wse.result_to_dict(1, {"title": "T", "url": "u", "text": None})
        assert row["snippet"] == ""


class TestFormatResult:
    def test_formats_three_lines(self):
        row = {"rank": 1, "title": "T", "url": "U", "snippet": "S"}
        assert wse.format_result(row) == "1. T\n   U\n   S"


class TestParseArgs:
    def test_defaults(self):
        args = wse.parse_args(["python"])
        assert args.query == "python"
        assert args.limit == wse.RESULTS_TO_SHOW
        assert args.json is False

    def test_flags(self):
        args = wse.parse_args(["python", "--limit", "5", "--json"])
        assert args.limit == 5
        assert args.json is True

    def test_invalid_limit_rejected(self):
        with pytest.raises(SystemExit):
            wse.parse_args(["python", "--limit", "0"])


class TestMain:
    def test_missing_api_key_exits_json(self, monkeypatch, capsys):
        monkeypatch.setattr(wse, "load_dotenv", lambda: None)
        monkeypatch.delenv("EXA_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            wse.main(["python", "--json"])
        assert exc.value.code == 1
        err = json.loads(capsys.readouterr().err)
        assert "EXA_API_KEY" in err["error"]

    def test_missing_api_key_exits_text(self, monkeypatch, capsys):
        monkeypatch.setattr(wse, "load_dotenv", lambda: None)
        monkeypatch.delenv("EXA_API_KEY", raising=False)
        with pytest.raises(SystemExit):
            wse.main(["python"])
        assert "EXA_API_KEY" in capsys.readouterr().err

    def test_request_error_exits_json(self, monkeypatch, capsys):
        monkeypatch.setattr(wse, "load_dotenv", lambda: None)
        monkeypatch.setenv("EXA_API_KEY", "key")

        def boom(*a, **k):
            raise requests.RequestException("network down")

        monkeypatch.setattr(wse, "fetch_results", boom)
        with pytest.raises(SystemExit) as exc:
            wse.main(["python", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "network down"}

    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(wse, "load_dotenv", lambda: None)
        monkeypatch.setenv("EXA_API_KEY", "key")
        monkeypatch.setattr(
            wse, "fetch_results",
            lambda q, l, k: [{"title": "A", "url": "u", "text": "d"}],
        )
        wse.main(["python", "--json"])
        rows = json.loads(capsys.readouterr().out)
        assert rows == [{"rank": 1, "title": "A", "url": "u", "snippet": "d"}]

    def test_no_results(self, monkeypatch, capsys):
        monkeypatch.setattr(wse, "load_dotenv", lambda: None)
        monkeypatch.setenv("EXA_API_KEY", "key")
        monkeypatch.setattr(wse, "fetch_results", lambda q, l, k: [])
        wse.main(["python"])
        assert "No results found." in capsys.readouterr().out

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(wse, "load_dotenv", lambda: None)
        monkeypatch.setenv("EXA_API_KEY", "key")
        monkeypatch.setattr(
            wse, "fetch_results",
            lambda q, l, k: [{"title": "A", "url": "u", "text": "d"}],
        )
        wse.main(["python"])
        out = capsys.readouterr().out
        assert "Searching for: python" in out
        assert "1. A" in out
        assert "u" in out
