"""Tests for url_metadata: GET request, metadata extraction, and main()."""

import json

import pytest
import requests

import url_metadata as um
from helpers import FakeResponse

PAGE = """<!doctype html>
<html><head>
  <title>
    Example   Page
  </title>
  <meta name="description" content="  A page  about examples. ">
  <link rel="canonical" href="/canonical-page">
  <meta property="og:title" content="OG Title">
  <meta property="og:image" content="/img/card.png">
  <meta property="og:url" content="https://example.com/canonical-page">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@example">
</head><body><p>Hi</p></body></html>
"""


def _result(**overrides):
    result = {
        "url": "https://example.com",
        "final_url": "https://example.com",
        "status_code": 200,
        "content_type": "text/html",
        "title": "Example Page",
        "description": "A page about examples.",
        "canonical": "https://example.com/canonical-page",
        "open_graph": {"title": "OG Title", "image": "https://example.com/img/card.png"},
        "twitter": {"card": "summary"},
    }
    result.update(overrides)
    return result


class TestExtractMetadata:
    def test_full_page(self):
        meta = um.extract_metadata(PAGE, "https://example.com/blog/post")
        assert meta == {
            "title": "Example Page",
            "description": "A page about examples.",
            "canonical": "https://example.com/canonical-page",
            "open_graph": {
                "title": "OG Title",
                "image": "https://example.com/img/card.png",
                "url": "https://example.com/canonical-page",
            },
            "twitter": {"card": "summary_large_image", "site": "@example"},
        }

    def test_empty_page(self):
        assert um.extract_metadata("<p>nothing</p>", "https://example.com") == {
            "title": None, "description": None, "canonical": None,
            "open_graph": {}, "twitter": {},
        }

    def test_head_title_preferred_over_svg_title(self):
        html = ("<html><head><title>Real</title></head>"
                "<body><svg><title>Icon</title></svg></body></html>")
        assert um.extract_metadata(html, "https://x.test")["title"] == "Real"

    def test_title_without_head(self):
        assert um.extract_metadata("<title>Bare</title>", "https://x.test")["title"] == "Bare"

    def test_blank_title_is_none(self):
        assert um.extract_metadata("<title>  </title>", "https://x.test")["title"] is None

    def test_meta_names_case_insensitive_and_either_attribute(self):
        html = ('<meta name="Description" content="D">'
                '<meta name="OG:Title" content="T">'
                '<meta property="twitter:card" content="summary">')
        meta = um.extract_metadata(html, "https://x.test")
        assert meta["description"] == "D"
        assert meta["open_graph"] == {"title": "T"}
        assert meta["twitter"] == {"card": "summary"}

    def test_first_value_wins(self):
        html = ('<meta property="og:image" content="https://x.test/1.png">'
                '<meta property="og:image" content="https://x.test/2.png">'
                '<meta name="description" content="first">'
                '<meta name="description" content="second">')
        meta = um.extract_metadata(html, "https://x.test")
        assert meta["open_graph"]["image"] == "https://x.test/1.png"
        assert meta["description"] == "first"

    def test_empty_content_skipped(self):
        html = '<meta property="og:title" content=" "><meta property="og:title" content="Kept">'
        assert um.extract_metadata(html, "https://x.test")["open_graph"] == {"title": "Kept"}

    def test_only_url_keys_resolved(self):
        html = ('<meta name="twitter:image" content="pic.png">'
                '<meta name="twitter:title" content="rel/looking">')
        meta = um.extract_metadata(html, "https://x.test/a/")
        assert meta["twitter"] == {"image": "https://x.test/a/pic.png", "title": "rel/looking"}

    def test_canonical_rel_among_several(self):
        html = ('<link rel="stylesheet" href="/s.css">'
                '<link rel="Canonical alternate" href="https://x.test/c">')
        assert um.extract_metadata(html, "https://x.test")["canonical"] == "https://x.test/c"

    def test_canonical_with_empty_href_ignored(self):
        html = '<link rel="canonical" href=" "><link rel="canonical" href="/real">'
        assert um.extract_metadata(html, "https://x.test")["canonical"] == "https://x.test/real"

    def test_other_meta_ignored(self):
        html = '<meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        meta = um.extract_metadata(html, "https://x.test")
        assert (meta["description"], meta["open_graph"], meta["twitter"]) == (None, {}, {})

    def test_missing_bs4_raises_import_error(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "bs4":
                raise ImportError("No module named 'bs4'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(ImportError):
            um.extract_metadata(PAGE, "https://example.com")


class TestFetchMetadata:
    def _response(self, **kwargs):
        headers = kwargs.pop("headers", {"Content-Type": "text/html; charset=utf-8"})
        kwargs.setdefault("status_code", 200)
        kwargs.setdefault("url", "https://example.com/")
        response = FakeResponse(**kwargs)
        response.headers = headers
        return response

    def test_basic_fetch(self, monkeypatch):
        response = self._response(text=PAGE)

        def fake_get(url, **kwargs):
            assert url == "https://example.com"
            assert kwargs["timeout"] == um.TIMEOUT_SECONDS
            assert kwargs["allow_redirects"] is True
            assert kwargs["headers"]["User-Agent"] == um.USER_AGENT
            return response

        monkeypatch.setattr(um.requests, "get", fake_get)
        result = um.fetch_metadata("https://example.com")
        assert result["url"] == "https://example.com"
        assert result["final_url"] == "https://example.com/"
        assert result["status_code"] == 200
        assert result["content_type"] == "text/html; charset=utf-8"
        assert result["title"] == "Example Page"
        assert result["twitter"]["card"] == "summary_large_image"

    def test_resolved_against_final_url(self, monkeypatch):
        response = self._response(
            text='<link rel="canonical" href="page">', url="https://example.com/sub/"
        )
        monkeypatch.setattr(um.requests, "get", lambda url, **kwargs: response)
        result = um.fetch_metadata("https://example.com/sub")
        assert result["canonical"] == "https://example.com/sub/page"

    def test_non_html_content_type_raises(self, monkeypatch):
        response = self._response(text="{}", headers={"Content-Type": "application/json"})
        monkeypatch.setattr(um.requests, "get", lambda url, **kwargs: response)
        with pytest.raises(ValueError, match="did not return HTML content"):
            um.fetch_metadata("https://example.com")

    def test_missing_content_type_raises(self, monkeypatch):
        response = self._response(text="hi", headers={})
        monkeypatch.setattr(um.requests, "get", lambda url, **kwargs: response)
        with pytest.raises(ValueError, match="Content-Type: unknown"):
            um.fetch_metadata("https://example.com")

    def test_http_error_raised(self, monkeypatch):
        response = self._response(
            status_code=404, reason="Not Found", raise_for_status=requests.HTTPError("404")
        )
        monkeypatch.setattr(um.requests, "get", lambda url, **kwargs: response)
        with pytest.raises(requests.HTTPError):
            um.fetch_metadata("https://example.com")

    def test_connection_error_propagates(self, monkeypatch):
        def fake_get(url, **kwargs):
            raise requests.ConnectionError("boom")

        monkeypatch.setattr(um.requests, "get", fake_get)
        with pytest.raises(requests.ConnectionError):
            um.fetch_metadata("https://example.com")

    def test_custom_timeout_passed_through(self, monkeypatch):
        captured = {}

        def fake_get(url, **kwargs):
            captured.update(kwargs)
            return self._response(text="<title>X</title>")

        monkeypatch.setattr(um.requests, "get", fake_get)
        um.fetch_metadata("https://example.com", timeout=3)
        assert captured["timeout"] == 3


class TestFormatResult:
    def test_full(self):
        out = um.format_result(_result())
        assert "Redirected to:" not in out
        assert "Status: 200" in out
        assert "Title:       Example Page" in out
        assert "Description: A page about examples." in out
        assert "Canonical:   https://example.com/canonical-page" in out
        assert "OpenGraph:\n  title  OG Title\n  image  https://example.com/img/card.png" in out
        assert "Twitter card:\n  card  summary" in out

    def test_redirect_shown(self):
        out = um.format_result(_result(url="http://example.com", final_url="https://example.com/"))
        assert "Redirected to: https://example.com/" in out

    def test_missing_fields(self):
        out = um.format_result(_result(title=None, description=None, canonical=None,
                                       open_graph={}, twitter={}))
        assert "Title:       -" in out
        assert "Description: -" in out
        assert "Canonical:   -" in out
        assert "OpenGraph: none" in out
        assert "Twitter card: none" in out


class TestParseArgs:
    def test_defaults(self):
        args = um.parse_args(["https://example.com"])
        assert args.url == "https://example.com"
        assert args.timeout == um.TIMEOUT_SECONDS
        assert args.json is False

    def test_flags(self):
        args = um.parse_args(["https://example.com", "--timeout", "5", "--json"])
        assert args.timeout == 5
        assert args.json is True

    def test_invalid_timeout_rejected(self):
        with pytest.raises(SystemExit) as exc:
            um.parse_args(["https://example.com", "--timeout", "0"])
        assert exc.value.code == 2


class TestMain:
    def test_rejects_missing_scheme_json(self, capsys):
        with pytest.raises(SystemExit) as exc:
            um.main(["example.com", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "URL must start with http:// or https://, got: example.com"
        }

    def test_rejects_missing_scheme_text(self, capsys):
        with pytest.raises(SystemExit):
            um.main(["example.com"])
        assert "must start with http" in capsys.readouterr().err

    def test_request_error_exits_json(self, monkeypatch, capsys):
        def boom(url, timeout):
            raise requests.ConnectionError("Name or service not known")

        monkeypatch.setattr(um, "fetch_metadata", boom)
        with pytest.raises(SystemExit) as exc:
            um.main(["https://nosuchhost.invalid", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "Name or service not known"}

    def test_value_error_exits_json(self, monkeypatch, capsys):
        def boom(url, timeout):
            raise ValueError("URL did not return HTML content (Content-Type: application/json)")

        monkeypatch.setattr(um, "fetch_metadata", boom)
        with pytest.raises(SystemExit) as exc:
            um.main(["https://example.com/data.json", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "URL did not return HTML content (Content-Type: application/json)"
        }

    def test_missing_bs4_exits_json(self, monkeypatch, capsys):
        def boom(url, timeout):
            raise ImportError("No module named 'bs4'")

        monkeypatch.setattr(um, "fetch_metadata", boom)
        with pytest.raises(SystemExit) as exc:
            um.main(["https://example.com", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "beautifulsoup4 is required (pip install beautifulsoup4)"
        }

    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(um, "fetch_metadata", lambda url, timeout: _result(url=url))
        um.main(["https://example.com", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["title"] == "Example Page"
        assert payload["open_graph"]["title"] == "OG Title"

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(um, "fetch_metadata", lambda url, timeout: _result(url=url))
        um.main(["https://example.com"])
        out = capsys.readouterr().out
        assert "Fetching: https://example.com" in out
        assert "Title:       Example Page" in out

    def test_timeout_passed_through(self, monkeypatch):
        captured = {}

        def fake_fetch(url, timeout):
            captured["timeout"] = timeout
            return _result(url=url)

        monkeypatch.setattr(um, "fetch_metadata", fake_fetch)
        um.main(["https://example.com", "--timeout", "3", "--json"])
        assert captured["timeout"] == 3
