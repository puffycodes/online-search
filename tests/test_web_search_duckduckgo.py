"""Tests for web_search_duckduckgo: fetch via DDGS, result flattening, and main()."""

import json

import pytest

import web_search_duckduckgo as wsd


class FakeDDGS:
    """Duck-type of ddgs.DDGS: a context manager exposing .text()."""

    def __init__(self, results=None, exception=None):
        self.results = results if results is not None else []
        self.exception = exception
        self.calls = []

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def text(self, query, max_results=None):
        self.calls.append((query, max_results))
        if self.exception is not None:
            raise self.exception
        return self.results


class TestFetchResults:
    def test_returns_list_of_results(self, monkeypatch):
        fake = FakeDDGS(results=[{"title": "A"}, {"title": "B"}, {"title": "C"}])
        monkeypatch.setattr(wsd, "DDGS", fake)
        results = wsd.fetch_results("python", 3)
        assert results == [{"title": "A"}, {"title": "B"}, {"title": "C"}]
        assert fake.calls == [("python", 3)]

    def test_propagates_ddgs_exception(self, monkeypatch):
        fake = FakeDDGS(exception=wsd.DDGSException("202 Ratelimit"))
        monkeypatch.setattr(wsd, "DDGS", fake)
        with pytest.raises(wsd.DDGSException):
            wsd.fetch_results("python", 3)


class TestResultToDict:
    def test_full_item(self):
        item = {"title": "Python", "href": "http://x", "body": "line1\nline2"}
        row = wsd.result_to_dict(1, item)
        assert row == {
            "rank": 1,
            "title": "Python",
            "url": "http://x",
            "snippet": "line1 line2",
        }

    def test_missing_fields_use_defaults(self):
        row = wsd.result_to_dict(2, {})
        assert row["title"] == "(no title)"
        assert row["url"] == ""
        assert row["snippet"] == ""


class TestFormatResult:
    def test_formats_three_lines(self):
        row = {"rank": 1, "title": "T", "url": "U", "snippet": "S"}
        assert wsd.format_result(row) == "1. T\n   U\n   S"


class TestParseArgs:
    def test_defaults(self):
        args = wsd.parse_args(["python"])
        assert args.query == "python"
        assert args.limit == wsd.RESULTS_TO_SHOW
        assert args.json is False

    def test_flags(self):
        args = wsd.parse_args(["python", "--limit", "5", "--json"])
        assert args.limit == 5
        assert args.json is True

    def test_invalid_limit_rejected(self):
        with pytest.raises(SystemExit):
            wsd.parse_args(["python", "--limit", "0"])


class TestMain:
    def test_missing_dependency_exits_json(self, monkeypatch, capsys):
        monkeypatch.setattr(wsd, "DDGS", None)
        with pytest.raises(SystemExit) as exc:
            wsd.main(["python", "--json"])
        assert exc.value.code == 1
        err = json.loads(capsys.readouterr().err)
        assert "ddgs" in err["error"]

    def test_missing_dependency_exits_text(self, monkeypatch, capsys):
        monkeypatch.setattr(wsd, "DDGS", None)
        with pytest.raises(SystemExit):
            wsd.main(["python"])
        assert "ddgs" in capsys.readouterr().err

    def test_search_error_exits_json(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise wsd.DDGSException("202 Ratelimit")

        monkeypatch.setattr(wsd, "fetch_results", boom)
        with pytest.raises(SystemExit) as exc:
            wsd.main(["python", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "202 Ratelimit"}

    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            wsd, "fetch_results",
            lambda q, l: [{"title": "A", "href": "u", "body": "d"}],
        )
        wsd.main(["python", "--json"])
        rows = json.loads(capsys.readouterr().out)
        assert rows == [{"rank": 1, "title": "A", "url": "u", "snippet": "d"}]

    def test_no_results(self, monkeypatch, capsys):
        monkeypatch.setattr(wsd, "fetch_results", lambda q, l: [])
        wsd.main(["python"])
        assert "No results found." in capsys.readouterr().out

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            wsd, "fetch_results",
            lambda q, l: [{"title": "A", "href": "u", "body": "d"}],
        )
        wsd.main(["python"])
        out = capsys.readouterr().out
        assert "Searching for: python" in out
        assert "1. A" in out
        assert "u" in out
