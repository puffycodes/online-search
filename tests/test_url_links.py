"""Tests for url_links: GET request, link extraction, and main()."""

import json

import pytest
import requests

import url_links as ul
from helpers import FakeResponse


class TestExtractLinks:
    def test_extracts_href_and_text(self):
        html = '<a href="/about">About us</a>'
        links = ul.extract_links(html, "https://example.com")
        assert links == [{"text": "About us", "url": "https://example.com/about"}]

    def test_resolves_relative_links(self):
        html = '<a href="../docs/page.html">Docs</a>'
        links = ul.extract_links(html, "https://example.com/blog/post")
        assert links[0]["url"] == "https://example.com/docs/page.html"

    def test_keeps_absolute_links_as_is(self):
        html = '<a href="https://other.example/">Other</a>'
        links = ul.extract_links(html, "https://example.com")
        assert links[0]["url"] == "https://other.example/"

    def test_skips_anchors_without_href(self):
        html = '<a name="top">Top</a><a href="/x">X</a>'
        links = ul.extract_links(html, "https://example.com")
        assert links == [{"text": "X", "url": "https://example.com/x"}]

    def test_skips_empty_href(self):
        html = '<a href="   ">Empty</a><a href="/x">X</a>'
        links = ul.extract_links(html, "https://example.com")
        assert links == [{"text": "X", "url": "https://example.com/x"}]

    def test_collapses_whitespace_in_text(self):
        html = '<a href="/x">\n  Hello \n  world  \n</a>'
        links = ul.extract_links(html, "https://example.com")
        assert links[0]["text"] == "Hello world"

    def test_missing_text_is_empty_string(self):
        html = '<a href="/x"><img src="icon.png"></a>'
        links = ul.extract_links(html, "https://example.com")
        assert links[0]["text"] == ""

    def test_keeps_mailto_tel_javascript_links(self):
        html = (
            '<a href="mailto:a@example.com">Mail</a>'
            '<a href="tel:+123">Call</a>'
            '<a href="javascript:void(0)">JS</a>'
        )
        links = ul.extract_links(html, "https://example.com")
        urls = [link["url"] for link in links]
        assert "mailto:a@example.com" in urls
        assert "tel:+123" in urls
        assert "javascript:void(0)" in urls

    def test_document_order_preserved(self):
        html = '<a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'
        links = ul.extract_links(html, "https://example.com")
        assert [link["url"] for link in links] == [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
        ]

    def test_no_links(self):
        assert ul.extract_links("<p>Nothing here</p>", "https://example.com") == []

    def test_missing_bs4_raises_import_error(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "bs4":
                raise ImportError("No module named 'bs4'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(ImportError):
            ul.extract_links('<a href="/x">X</a>', "https://example.com")


class TestFetchLinks:
    def _response(self, **kwargs):
        headers = kwargs.pop("headers", {"Content-Type": "text/html"})
        kwargs.setdefault("status_code", 200)
        kwargs.setdefault("url", "https://example.com/")
        response = FakeResponse(**kwargs)
        response.headers = headers
        return response

    def test_basic_fetch(self, monkeypatch):
        response = self._response(text='<a href="/about">About</a>')

        def fake_get(url, **kwargs):
            assert url == "https://example.com"
            assert kwargs["timeout"] == ul.TIMEOUT_SECONDS
            assert kwargs["allow_redirects"] is True
            return response

        monkeypatch.setattr(ul.requests, "get", fake_get)
        result = ul.fetch_links("https://example.com")
        assert result["url"] == "https://example.com"
        assert result["final_url"] == "https://example.com/"
        assert result["status_code"] == 200
        assert result["content_type"] == "text/html"
        assert result["link_count"] == 1
        assert result["links"] == [
            {"text": "About", "url": "https://example.com/about"}
        ]

    def test_links_resolved_against_final_url(self, monkeypatch):
        response = self._response(
            text='<a href="page">Page</a>', url="https://example.com/sub/"
        )
        monkeypatch.setattr(ul.requests, "get", lambda url, **kwargs: response)
        result = ul.fetch_links("https://example.com/sub")
        assert result["links"][0]["url"] == "https://example.com/sub/page"

    def test_non_html_content_type_raises(self, monkeypatch):
        response = self._response(text="{}", headers={"Content-Type": "application/json"})
        monkeypatch.setattr(ul.requests, "get", lambda url, **kwargs: response)
        with pytest.raises(ValueError, match="did not return HTML content"):
            ul.fetch_links("https://example.com")

    def test_missing_content_type_raises(self, monkeypatch):
        response = self._response(text="hi", headers={})
        monkeypatch.setattr(ul.requests, "get", lambda url, **kwargs: response)
        with pytest.raises(ValueError, match="Content-Type: unknown"):
            ul.fetch_links("https://example.com")

    def test_http_error_raised(self, monkeypatch):
        response = self._response(
            status_code=404, reason="Not Found", raise_for_status=requests.HTTPError("404")
        )
        monkeypatch.setattr(ul.requests, "get", lambda url, **kwargs: response)
        with pytest.raises(requests.HTTPError):
            ul.fetch_links("https://example.com")

    def test_connection_error_propagates(self, monkeypatch):
        def fake_get(url, **kwargs):
            raise requests.ConnectionError("boom")

        monkeypatch.setattr(ul.requests, "get", fake_get)
        with pytest.raises(requests.ConnectionError):
            ul.fetch_links("https://example.com")

    def test_custom_timeout_passed_through(self, monkeypatch):
        captured = {}

        def fake_get(url, **kwargs):
            captured.update(kwargs)
            return self._response(text="<a href='/x'>X</a>")

        monkeypatch.setattr(ul.requests, "get", fake_get)
        ul.fetch_links("https://example.com", timeout=3)
        assert captured["timeout"] == 3

    def test_no_links_found(self, monkeypatch):
        response = self._response(text="<p>Nothing</p>")
        monkeypatch.setattr(ul.requests, "get", lambda url, **kwargs: response)
        result = ul.fetch_links("https://example.com")
        assert result["link_count"] == 0
        assert result["links"] == []


class TestFormatResult:
    def test_no_redirect(self):
        result = {
            "url": "https://example.com",
            "final_url": "https://example.com",
            "status_code": 200,
            "content_type": "text/html",
            "link_count": 1,
            "links": [{"text": "About", "url": "https://example.com/about"}],
        }
        out = ul.format_result(result)
        assert "Redirected to:" not in out
        assert "Status: 200" in out
        assert "Links found: 1" in out
        assert "1. About" in out
        assert "https://example.com/about" in out

    def test_redirect_shown(self):
        result = {
            "url": "http://example.com",
            "final_url": "https://example.com/",
            "status_code": 200,
            "content_type": "text/html",
            "link_count": 0,
            "links": [],
        }
        out = ul.format_result(result)
        assert "Redirected to: https://example.com/" in out
        assert "Links found: 0" in out

    def test_link_with_no_text(self):
        result = {
            "url": "https://example.com",
            "final_url": "https://example.com",
            "status_code": 200,
            "content_type": "text/html",
            "link_count": 1,
            "links": [{"text": "", "url": "https://example.com/x"}],
        }
        out = ul.format_result(result)
        assert "(no text)" in out


class TestParseArgs:
    def test_defaults(self):
        args = ul.parse_args(["https://example.com"])
        assert args.url == "https://example.com"
        assert args.timeout == ul.TIMEOUT_SECONDS
        assert args.json is False

    def test_flags(self):
        args = ul.parse_args(["https://example.com", "--timeout", "5", "--json"])
        assert args.timeout == 5
        assert args.json is True

    def test_invalid_timeout_rejected(self):
        with pytest.raises(SystemExit) as exc:
            ul.parse_args(["https://example.com", "--timeout", "0"])
        assert exc.value.code == 2


class TestMain:
    def test_rejects_missing_scheme_json(self, capsys):
        with pytest.raises(SystemExit) as exc:
            ul.main(["example.com", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "URL must start with http:// or https://, got: example.com"
        }

    def test_rejects_missing_scheme_text(self, capsys):
        with pytest.raises(SystemExit):
            ul.main(["example.com"])
        assert "must start with http" in capsys.readouterr().err

    def test_request_error_exits_json(self, monkeypatch, capsys):
        def boom(url, timeout):
            raise requests.ConnectionError("Name or service not known")

        monkeypatch.setattr(ul, "fetch_links", boom)
        with pytest.raises(SystemExit) as exc:
            ul.main(["https://nosuchhost.invalid", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "Name or service not known"
        }

    def test_value_error_exits_json(self, monkeypatch, capsys):
        def boom(url, timeout):
            raise ValueError("URL did not return HTML content (Content-Type: application/json)")

        monkeypatch.setattr(ul, "fetch_links", boom)
        with pytest.raises(SystemExit) as exc:
            ul.main(["https://example.com/data.json", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "URL did not return HTML content (Content-Type: application/json)"
        }

    def test_missing_bs4_exits_json(self, monkeypatch, capsys):
        def boom(url, timeout):
            raise ImportError("No module named 'bs4'")

        monkeypatch.setattr(ul, "fetch_links", boom)
        with pytest.raises(SystemExit) as exc:
            ul.main(["https://example.com", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "beautifulsoup4 is required (pip install beautifulsoup4)"
        }

    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            ul,
            "fetch_links",
            lambda url, timeout: {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": "text/html",
                "link_count": 1,
                "links": [{"text": "X", "url": "https://example.com/x"}],
            },
        )
        ul.main(["https://example.com", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["link_count"] == 1
        assert payload["links"][0]["url"] == "https://example.com/x"

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            ul,
            "fetch_links",
            lambda url, timeout: {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": "text/html",
                "link_count": 1,
                "links": [{"text": "X", "url": "https://example.com/x"}],
            },
        )
        ul.main(["https://example.com"])
        out = capsys.readouterr().out
        assert "Fetching: https://example.com" in out
        assert "Status: 200" in out
        assert "1. X" in out

    def test_timeout_passed_through(self, monkeypatch, capsys):
        captured = {}

        def fake_fetch(url, timeout):
            captured["timeout"] = timeout
            return {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": "text/html",
                "link_count": 0,
                "links": [],
            }

        monkeypatch.setattr(ul, "fetch_links", fake_fetch)
        ul.main(["https://example.com", "--timeout", "3", "--json"])
        assert captured["timeout"] == 3
