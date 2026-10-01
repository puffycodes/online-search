"""Tests for web_search_perplexity: dotenv loading, answer fetching, and main()."""

import json
import os

import pytest
import requests

import web_search_perplexity as wsp
from helpers import FakeResponse


class TestLoadDotenv:
    def test_missing_file_is_silently_ignored(self, tmp_path):
        wsp.load_dotenv(path=str(tmp_path / "nope.env"))

    def test_populates_environ(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WSP_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("WSP_TEST_KEY=abc123\n# a comment\n\nBAD_LINE_NO_EQUALS\n")
        wsp.load_dotenv(path=str(env_file))
        assert os.environ["WSP_TEST_KEY"] == "abc123"

    def test_quoted_value_is_unquoted(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WSP_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text('WSP_TEST_KEY="quoted value"\n')
        wsp.load_dotenv(path=str(env_file))
        assert os.environ["WSP_TEST_KEY"] == "quoted value"

    def test_real_env_var_takes_precedence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WSP_TEST_KEY", "real")
        env_file = tmp_path / ".env"
        env_file.write_text("WSP_TEST_KEY=fromfile\n")
        wsp.load_dotenv(path=str(env_file))
        assert os.environ["WSP_TEST_KEY"] == "real"


class TestFetchAnswer:
    def test_returns_answer_and_sources(self, monkeypatch):
        response = FakeResponse(
            json_data={
                "choices": [{"message": {"content": "The answer."}}],
                "search_results": [{"title": "A", "url": "u1"}],
            }
        )
        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs)
            return response

        monkeypatch.setattr(wsp.requests, "post", fake_post)
        answer, sources = wsp.fetch_answer("q", "key")
        assert answer == "The answer."
        assert sources == [{"title": "A", "url": "u1"}]
        assert calls[0]["headers"]["Authorization"] == "Bearer key"
        assert calls[0]["json"]["model"] == wsp.DEFAULT_MODEL
        assert calls[0]["json"]["messages"] == [{"role": "user", "content": "q"}]

    def test_custom_model_passed_through(self, monkeypatch):
        response = FakeResponse(
            json_data={"choices": [{"message": {"content": "A"}}]}
        )
        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs)
            return response

        monkeypatch.setattr(wsp.requests, "post", fake_post)
        wsp.fetch_answer("q", "key", model="sonar-pro")
        assert calls[0]["json"]["model"] == "sonar-pro"

    def test_missing_search_results_returns_empty_list(self, monkeypatch):
        response = FakeResponse(
            json_data={"choices": [{"message": {"content": "A"}}]}
        )
        monkeypatch.setattr(wsp.requests, "post", lambda url, **kw: response)
        _, sources = wsp.fetch_answer("q", "key")
        assert sources == []

    def test_raise_for_status_propagates(self, monkeypatch):
        response = FakeResponse(raise_for_status=requests.HTTPError("401"))
        monkeypatch.setattr(wsp.requests, "post", lambda url, **kw: response)
        with pytest.raises(requests.HTTPError):
            wsp.fetch_answer("q", "key")

    def test_empty_choices_raises(self, monkeypatch):
        response = FakeResponse(json_data={"choices": []})
        monkeypatch.setattr(wsp.requests, "post", lambda url, **kw: response)
        with pytest.raises(requests.RequestException, match="no answer"):
            wsp.fetch_answer("q", "key")

    @pytest.mark.parametrize("content", ["", "   ", None])
    def test_empty_answer_raises(self, monkeypatch, content):
        response = FakeResponse(json_data={"choices": [{"message": {"content": content}}]})
        monkeypatch.setattr(wsp.requests, "post", lambda url, **kw: response)
        with pytest.raises(requests.RequestException, match="no answer"):
            wsp.fetch_answer("q", "key")

    def test_missing_choices_key_raises(self, monkeypatch):
        response = FakeResponse(json_data={})
        monkeypatch.setattr(wsp.requests, "post", lambda url, **kw: response)
        with pytest.raises(requests.RequestException, match="no answer"):
            wsp.fetch_answer("q", "key")


class TestSourceToDict:
    def test_maps_fields(self):
        item = {"title": "Python", "url": "http://x", "date": "2026-01-01"}
        row = wsp.source_to_dict(1, item)
        assert row == {
            "rank": 1,
            "title": "Python",
            "url": "http://x",
            "date": "2026-01-01",
        }

    def test_missing_fields_use_defaults(self):
        row = wsp.source_to_dict(2, {})
        assert row["title"] == "(no title)"
        assert row["url"] == ""
        assert row["date"] is None


class TestFormatAnswer:
    def test_includes_answer_and_sources(self):
        sources = [
            {"rank": 1, "title": "A", "url": "u1", "date": "2026-01-01"},
            {"rank": 2, "title": "B", "url": "u2", "date": None},
        ]
        text = wsp.format_answer("  The answer.  ", sources)
        assert text.startswith("The answer.")
        assert "Sources:" in text
        assert "1. A (2026-01-01)" in text
        assert "2. B" in text
        assert "u1" in text and "u2" in text

    def test_no_sources_omits_sources_heading(self):
        text = wsp.format_answer("The answer.", [])
        assert text == "The answer."
        assert "Sources:" not in text


class TestParseArgs:
    def test_defaults(self):
        args = wsp.parse_args(["query text"])
        assert args.query == "query text"
        assert args.model == wsp.DEFAULT_MODEL
        assert args.limit == wsp.SOURCES_TO_SHOW
        assert args.json is False

    def test_flags(self):
        args = wsp.parse_args(
            ["query text", "--model", "sonar-pro", "--limit", "3", "--json"]
        )
        assert args.model == "sonar-pro"
        assert args.limit == 3
        assert args.json is True

    def test_invalid_limit_rejected(self):
        with pytest.raises(SystemExit):
            wsp.parse_args(["query", "--limit", "0"])


class TestMain:
    def test_missing_api_key_exits_json(self, monkeypatch, capsys):
        monkeypatch.setattr(wsp, "load_dotenv", lambda: None)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            wsp.main(["query", "--json"])
        assert exc.value.code == 1
        err = json.loads(capsys.readouterr().err)
        assert "PERPLEXITY_API_KEY" in err["error"]

    def test_missing_api_key_exits_text(self, monkeypatch, capsys):
        monkeypatch.setattr(wsp, "load_dotenv", lambda: None)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        with pytest.raises(SystemExit):
            wsp.main(["query"])
        assert "PERPLEXITY_API_KEY" in capsys.readouterr().err

    def test_request_error_exits_json(self, monkeypatch, capsys):
        monkeypatch.setattr(wsp, "load_dotenv", lambda: None)
        monkeypatch.setenv("PERPLEXITY_API_KEY", "key")

        def boom(*a, **k):
            raise requests.RequestException("network down")

        monkeypatch.setattr(wsp, "fetch_answer", boom)
        with pytest.raises(SystemExit) as exc:
            wsp.main(["query", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "network down"}

    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(wsp, "load_dotenv", lambda: None)
        monkeypatch.setenv("PERPLEXITY_API_KEY", "key")
        monkeypatch.setattr(
            wsp, "fetch_answer",
            lambda q, k, model=wsp.DEFAULT_MODEL: ("The answer.", [{"title": "A", "url": "u"}]),
        )
        wsp.main(["query", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload == {
            "answer": "The answer.",
            "sources": [{"rank": 1, "title": "A", "url": "u", "date": None}],
        }

    def test_limit_trims_sources(self, monkeypatch, capsys):
        monkeypatch.setattr(wsp, "load_dotenv", lambda: None)
        monkeypatch.setenv("PERPLEXITY_API_KEY", "key")
        many_sources = [{"title": str(i), "url": str(i)} for i in range(5)]
        monkeypatch.setattr(
            wsp, "fetch_answer",
            lambda q, k, model=wsp.DEFAULT_MODEL: ("A", many_sources),
        )
        wsp.main(["query", "--limit", "2", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["sources"]) == 2

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(wsp, "load_dotenv", lambda: None)
        monkeypatch.setenv("PERPLEXITY_API_KEY", "key")
        monkeypatch.setattr(
            wsp, "fetch_answer",
            lambda q, k, model=wsp.DEFAULT_MODEL: ("The answer.", [{"title": "A", "url": "u"}]),
        )
        wsp.main(["query"])
        out = capsys.readouterr().out
        assert "Asking: query" in out
        assert "The answer." in out
        assert "1. A" in out
        assert "u" in out
