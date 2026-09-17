"""Tests for url_content: GET request, content decoding, and main()."""

import json

import pytest
import requests

import url_content as uc
from helpers import FakeResponse


class TestIsTextContentType:
    def test_missing_is_text(self):
        assert uc.is_text_content_type(None) is True
        assert uc.is_text_content_type("") is True

    def test_text_html(self):
        assert uc.is_text_content_type("text/html; charset=utf-8") is True

    def test_json(self):
        assert uc.is_text_content_type("application/json") is True

    def test_xml(self):
        assert uc.is_text_content_type("application/xml") is True

    def test_javascript(self):
        assert uc.is_text_content_type("application/javascript") is True

    def test_binary_rejected(self):
        assert uc.is_text_content_type("image/png") is False
        assert uc.is_text_content_type("application/pdf") is False
        assert uc.is_text_content_type("application/octet-stream") is False


class TestExtractText:
    def test_strips_tags(self):
        html = "<html><body><h1>Title</h1><p>Hello <b>world</b>.</p></body></html>"
        assert uc.extract_text(html) == "Title Hello world ."

    def test_drops_script_and_style(self):
        html = (
            "<html><head><style>body{color:red}</style></head>"
            "<body><script>alert('hi')</script><p>Visible text</p></body></html>"
        )
        text = uc.extract_text(html)
        assert text == "Visible text"

    def test_collapses_whitespace(self):
        html = "<div>\n\n  <p>One</p>\n\n\n<p>Two</p>\n\n</div>"
        assert uc.extract_text(html) == "One Two"

    def test_missing_bs4_raises_import_error(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "bs4":
                raise ImportError("No module named 'bs4'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(ImportError):
            uc.extract_text("<p>hi</p>")


class TestFetchContent:
    def _response(self, **kwargs):
        headers = kwargs.pop("headers", {"Content-Type": "text/html"})
        kwargs.setdefault("status_code", 200)
        kwargs.setdefault("url", "https://example.com/")
        response = FakeResponse(**kwargs)
        response.headers = headers
        return response

    def test_basic_fetch(self, monkeypatch):
        response = self._response(text="<html>hi</html>")

        def fake_get(url, **kwargs):
            assert url == "https://example.com"
            assert kwargs["timeout"] == uc.TIMEOUT_SECONDS
            assert kwargs["allow_redirects"] is True
            return response

        monkeypatch.setattr(uc.requests, "get", fake_get)
        result = uc.fetch_content("https://example.com")
        assert result["url"] == "https://example.com"
        assert result["final_url"] == "https://example.com/"
        assert result["status_code"] == 200
        assert result["content_type"] == "text/html"
        assert result["content"] == "<html>hi</html>"
        assert result["length"] == len("<html>hi</html>")
        assert result["truncated"] is False

    def test_truncates_long_content(self, monkeypatch):
        long_text = "x" * 100
        response = self._response(text=long_text)
        monkeypatch.setattr(uc.requests, "get", lambda url, **kwargs: response)
        result = uc.fetch_content("https://example.com", max_chars=10)
        assert result["content"] == "x" * 10
        assert result["length"] == 100
        assert result["truncated"] is True

    def test_missing_content_type_treated_as_text(self, monkeypatch):
        response = self._response(text="hello", headers={})
        monkeypatch.setattr(uc.requests, "get", lambda url, **kwargs: response)
        result = uc.fetch_content("https://example.com")
        assert result["content_type"] is None
        assert result["content"] == "hello"

    def test_binary_content_type_raises(self, monkeypatch):
        response = self._response(text="\x89PNG...", headers={"Content-Type": "image/png"})
        monkeypatch.setattr(uc.requests, "get", lambda url, **kwargs: response)
        with pytest.raises(ValueError, match="did not return text content"):
            uc.fetch_content("https://example.com")

    def test_http_error_raised(self, monkeypatch):
        response = self._response(
            status_code=404, reason="Not Found", raise_for_status=requests.HTTPError("404")
        )
        monkeypatch.setattr(uc.requests, "get", lambda url, **kwargs: response)
        with pytest.raises(requests.HTTPError):
            uc.fetch_content("https://example.com")

    def test_connection_error_propagates(self, monkeypatch):
        def fake_get(url, **kwargs):
            raise requests.ConnectionError("boom")

        monkeypatch.setattr(uc.requests, "get", fake_get)
        with pytest.raises(requests.ConnectionError):
            uc.fetch_content("https://example.com")

    def test_custom_timeout_passed_through(self, monkeypatch):
        captured = {}

        def fake_get(url, **kwargs):
            captured.update(kwargs)
            return self._response(text="hi")

        monkeypatch.setattr(uc.requests, "get", fake_get)
        uc.fetch_content("https://example.com", timeout=3)
        assert captured["timeout"] == 3

    def test_as_text_extracts_and_flags_result(self, monkeypatch):
        response = self._response(text="<html><body><p>Hello world.</p></body></html>")
        monkeypatch.setattr(uc.requests, "get", lambda url, **kwargs: response)
        result = uc.fetch_content("https://example.com", as_text=True)
        assert result["content"] == "Hello world."
        assert result["length"] == len("Hello world.")
        assert result["text_extracted"] is True

    def test_default_does_not_extract(self, monkeypatch):
        response = self._response(text="<p>Hello world.</p>")
        monkeypatch.setattr(uc.requests, "get", lambda url, **kwargs: response)
        result = uc.fetch_content("https://example.com")
        assert result["content"] == "<p>Hello world.</p>"
        assert result["text_extracted"] is False


class TestFormatResult:
    def test_no_redirect(self):
        result = {
            "url": "https://example.com",
            "final_url": "https://example.com",
            "status_code": 200,
            "content_type": "text/html",
            "length": 5,
            "truncated": False,
            "content": "hello",
        }
        out = uc.format_result(result)
        assert "Redirected to:" not in out
        assert "Status: 200" in out
        assert "Content-Type: text/html" in out
        assert "Length: 5 characters" in out
        assert "(truncated)" not in out
        assert out.endswith("hello")

    def test_redirect_and_truncated_shown(self):
        result = {
            "url": "http://example.com",
            "final_url": "https://example.com/",
            "status_code": 200,
            "content_type": "text/html",
            "length": 100000,
            "truncated": True,
            "content": "x" * 20000,
        }
        out = uc.format_result(result)
        assert "Redirected to: https://example.com/" in out
        assert "Length: 100000 characters (truncated)" in out


class TestParseArgs:
    def test_defaults(self):
        args = uc.parse_args(["https://example.com"])
        assert args.url == "https://example.com"
        assert args.timeout == uc.TIMEOUT_SECONDS
        assert args.max_chars == uc.MAX_CHARS
        assert args.text is False
        assert args.json is False

    def test_flags(self):
        args = uc.parse_args(
            ["https://example.com", "--timeout", "5", "--max-chars", "100", "--text", "--json"]
        )
        assert args.timeout == 5
        assert args.max_chars == 100
        assert args.text is True
        assert args.json is True

    def test_invalid_timeout_rejected(self):
        with pytest.raises(SystemExit) as exc:
            uc.parse_args(["https://example.com", "--timeout", "0"])
        assert exc.value.code == 2

    def test_invalid_max_chars_rejected(self):
        with pytest.raises(SystemExit) as exc:
            uc.parse_args(["https://example.com", "--max-chars", "0"])
        assert exc.value.code == 2


class TestMain:
    def test_rejects_missing_scheme_json(self, capsys):
        with pytest.raises(SystemExit) as exc:
            uc.main(["example.com", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "URL must start with http:// or https://, got: example.com"
        }

    def test_rejects_missing_scheme_text(self, capsys):
        with pytest.raises(SystemExit):
            uc.main(["example.com"])
        assert "must start with http" in capsys.readouterr().err

    def test_request_error_exits_json(self, monkeypatch, capsys):
        def boom(url, timeout, max_chars, as_text):
            raise requests.ConnectionError("Name or service not known")

        monkeypatch.setattr(uc, "fetch_content", boom)
        with pytest.raises(SystemExit) as exc:
            uc.main(["https://nosuchhost.invalid", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "Name or service not known"
        }

    def test_value_error_exits_json(self, monkeypatch, capsys):
        def boom(url, timeout, max_chars, as_text):
            raise ValueError("URL did not return text content (Content-Type: image/png)")

        monkeypatch.setattr(uc, "fetch_content", boom)
        with pytest.raises(SystemExit) as exc:
            uc.main(["https://example.com/pic.png", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "URL did not return text content (Content-Type: image/png)"
        }

    def test_missing_bs4_exits_json(self, monkeypatch, capsys):
        def boom(url, timeout, max_chars, as_text):
            raise ImportError("No module named 'bs4'")

        monkeypatch.setattr(uc, "fetch_content", boom)
        with pytest.raises(SystemExit) as exc:
            uc.main(["https://example.com", "--text", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "beautifulsoup4 is required for --text (pip install beautifulsoup4)"
        }

    def test_missing_bs4_exits_text(self, monkeypatch, capsys):
        def boom(url, timeout, max_chars, as_text):
            raise ImportError("No module named 'bs4'")

        monkeypatch.setattr(uc, "fetch_content", boom)
        with pytest.raises(SystemExit):
            uc.main(["https://example.com", "--text"])
        assert "beautifulsoup4 is required" in capsys.readouterr().err

    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            uc,
            "fetch_content",
            lambda url, timeout, max_chars, as_text: {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": "text/html",
                "length": 5,
                "truncated": False,
                "text_extracted": as_text,
                "content": "hello",
            },
        )
        uc.main(["https://example.com", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["content"] == "hello"
        assert payload["status_code"] == 200
        assert payload["text_extracted"] is False

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            uc,
            "fetch_content",
            lambda url, timeout, max_chars, as_text: {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": "text/plain",
                "length": 2,
                "truncated": False,
                "text_extracted": as_text,
                "content": "hi",
            },
        )
        uc.main(["https://example.com"])
        out = capsys.readouterr().out
        assert "Fetching: https://example.com" in out
        assert "Status: 200" in out
        assert out.strip().endswith("hi")

    def test_text_flag_passed_through(self, monkeypatch, capsys):
        captured = {}

        def fake_fetch(url, timeout, max_chars, as_text):
            captured["as_text"] = as_text
            return {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": "text/html",
                "length": 2,
                "truncated": False,
                "text_extracted": as_text,
                "content": "hi",
            }

        monkeypatch.setattr(uc, "fetch_content", fake_fetch)
        uc.main(["https://example.com", "--text", "--json"])
        assert captured["as_text"] is True
        payload = json.loads(capsys.readouterr().out)
        assert payload["text_extracted"] is True
