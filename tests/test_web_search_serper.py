"""Tests for web_search_serper: dotenv loading, fetch pagination, and main()."""

import json
import os

import pytest
import requests

import web_search_serper as wss
from helpers import FakeResponse


class TestLoadDotenv:
    def test_missing_file_is_silently_ignored(self, tmp_path):
        wss.load_dotenv(path=str(tmp_path / "nope.env"))

    def test_populates_environ(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WSS_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("WSS_TEST_KEY=abc123\n# a comment\n\nBAD_LINE_NO_EQUALS\n")
        wss.load_dotenv(path=str(env_file))
        assert os.environ["WSS_TEST_KEY"] == "abc123"

    def test_quoted_value_is_unquoted(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WSS_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text('WSS_TEST_KEY="quoted value"\n')
        wss.load_dotenv(path=str(env_file))
        assert os.environ["WSS_TEST_KEY"] == "quoted value"

    def test_real_env_var_takes_precedence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WSS_TEST_KEY", "real")
        env_file = tmp_path / ".env"
        env_file.write_text("WSS_TEST_KEY=fromfile\n")
        wss.load_dotenv(path=str(env_file))
        assert os.environ["WSS_TEST_KEY"] == "real"


class TestFetchResults:
    def test_single_page(self, monkeypatch):
        response = FakeResponse(json_data={"organic": [{"title": "A"}, {"title": "B"}]})
        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs)
            return response

        monkeypatch.setattr(wss.requests, "post", fake_post)
        results = wss.fetch_results("q", 2, "key")
        assert results == [{"title": "A"}, {"title": "B"}]
        assert len(calls) == 1
        assert calls[0]["json"]["num"] == 2
        assert calls[0]["json"]["page"] == 1
        assert calls[0]["json"]["q"] == "q"
        assert calls[0]["headers"]["X-API-KEY"] == "key"

    def test_paginates_when_page_is_full(self, monkeypatch):
        page_size = wss.MAX_RESULTS_PER_REQUEST
        page1 = FakeResponse(
            json_data={"organic": [{"title": str(i)} for i in range(page_size)]}
        )
        page2 = FakeResponse(
            json_data={"organic": [{"title": "extra1"}, {"title": "extra2"}]}
        )
        responses = [page1, page2]
        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        monkeypatch.setattr(wss.requests, "post", fake_post)
        results = wss.fetch_results("q", page_size + 2, "key")
        assert len(results) == page_size + 2
        assert results[-1]["title"] == "extra2"
        assert calls[1]["json"]["page"] == 2

    def test_stops_when_fewer_results_than_requested(self, monkeypatch):
        response = FakeResponse(json_data={"organic": [{"title": "A"}]})
        monkeypatch.setattr(wss.requests, "post", lambda url, **kw: response)
        results = wss.fetch_results("q", 10, "key")
        assert results == [{"title": "A"}]

    def test_truncates_to_limit(self, monkeypatch):
        response = FakeResponse(
            json_data={"organic": [{"title": str(i)} for i in range(5)]}
        )
        monkeypatch.setattr(wss.requests, "post", lambda url, **kw: response)
        results = wss.fetch_results("q", 3, "key")
        assert len(results) == 3

    def test_raise_for_status_propagates(self, monkeypatch):
        response = FakeResponse(raise_for_status=requests.HTTPError("500"))
        monkeypatch.setattr(wss.requests, "post", lambda url, **kw: response)
        with pytest.raises(requests.HTTPError):
            wss.fetch_results("q", 1, "key")

    def test_message_field_without_organic_raises(self, monkeypatch):
        response = FakeResponse(json_data={"message": "Not enough credits."})
        monkeypatch.setattr(wss.requests, "post", lambda url, **kw: response)
        with pytest.raises(requests.RequestException, match="Not enough credits."):
            wss.fetch_results("q", 1, "key")


class TestResultToDict:
    def test_maps_link_and_joins_snippet_lines(self):
        item = {
            "title": "Python",
            "link": "http://x",
            "snippet": "first line\nsecond line",
        }
        row = wss.result_to_dict(1, item)
        assert row == {
            "rank": 1,
            "title": "Python",
            "url": "http://x",
            "snippet": "first line second line",
        }

    def test_missing_fields_use_defaults(self):
        row = wss.result_to_dict(2, {})
        assert row["title"] == "(no title)"
        assert row["url"] == ""
        assert row["snippet"] == ""


class TestParseArgs:
    def test_defaults(self):
        args = wss.parse_args(["python"])
        assert args.query == "python"
        assert args.limit == wss.RESULTS_TO_SHOW
        assert args.json is False

    def test_flags(self):
        args = wss.parse_args(["python", "--limit", "5", "--json"])
        assert args.limit == 5
        assert args.json is True

    def test_invalid_limit_rejected(self):
        with pytest.raises(SystemExit):
            wss.parse_args(["python", "--limit", "0"])


class TestMain:
    def test_missing_api_key_exits_json(self, monkeypatch, capsys):
        monkeypatch.setattr(wss, "load_dotenv", lambda: None)
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            wss.main(["python", "--json"])
        assert exc.value.code == 1
        err = json.loads(capsys.readouterr().err)
        assert "SERPER_API_KEY" in err["error"]

    def test_missing_api_key_exits_text(self, monkeypatch, capsys):
        monkeypatch.setattr(wss, "load_dotenv", lambda: None)
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        with pytest.raises(SystemExit):
            wss.main(["python"])
        assert "SERPER_API_KEY" in capsys.readouterr().err

    def test_request_error_exits_json(self, monkeypatch, capsys):
        monkeypatch.setattr(wss, "load_dotenv", lambda: None)
        monkeypatch.setenv("SERPER_API_KEY", "key")

        def boom(*a, **k):
            raise requests.RequestException("network down")

        monkeypatch.setattr(wss, "fetch_results", boom)
        with pytest.raises(SystemExit) as exc:
            wss.main(["python", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "network down"}

    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(wss, "load_dotenv", lambda: None)
        monkeypatch.setenv("SERPER_API_KEY", "key")
        monkeypatch.setattr(
            wss, "fetch_results",
            lambda q, l, k: [{"title": "A", "link": "u", "snippet": "d"}],
        )
        wss.main(["python", "--json"])
        rows = json.loads(capsys.readouterr().out)
        assert rows == [{"rank": 1, "title": "A", "url": "u", "snippet": "d"}]

    def test_no_results(self, monkeypatch, capsys):
        monkeypatch.setattr(wss, "load_dotenv", lambda: None)
        monkeypatch.setenv("SERPER_API_KEY", "key")
        monkeypatch.setattr(wss, "fetch_results", lambda q, l, k: [])
        wss.main(["python"])
        assert "No results found." in capsys.readouterr().out

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(wss, "load_dotenv", lambda: None)
        monkeypatch.setenv("SERPER_API_KEY", "key")
        monkeypatch.setattr(
            wss, "fetch_results",
            lambda q, l, k: [{"title": "A", "link": "u", "snippet": "d"}],
        )
        wss.main(["python"])
        out = capsys.readouterr().out
        assert "Searching for: python" in out
        assert "1. A" in out
        assert "u" in out
