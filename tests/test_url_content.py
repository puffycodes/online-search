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


class TestTitle:
    PAGE = "<html><head><title> My  Page </title></head><body><p>Body.</p></body></html>"

    def _fetch(self, monkeypatch, text, headers=None, **kwargs):
        response = FakeResponse(status_code=200, url="https://example.com/", text=text)
        response.headers = {"Content-Type": "text/html"} if headers is None else headers
        monkeypatch.setattr(uc.requests, "get", lambda url, **kw: response)
        return uc.fetch_content("https://example.com", **kwargs)

    def test_page_title_from_title_tag(self):
        assert uc.page_title(self.PAGE, "https://x.test") == "My Page"

    def test_page_title_falls_back_to_og_title(self):
        html = '<head><meta property="og:title" content="OG Name"></head>'
        assert uc.page_title(html, "https://x.test") == "OG Name"

    def test_page_title_none_without_either(self):
        assert uc.page_title("<p>no title</p>", "https://x.test") is None

    def test_text_mode_reports_title(self, monkeypatch):
        result = self._fetch(monkeypatch, self.PAGE, as_text=True)
        assert result["title"] == "My Page"
        assert result["content"] == "My Page Body."

    def test_title_with_missing_content_type(self, monkeypatch):
        assert self._fetch(monkeypatch, self.PAGE, headers={}, as_text=True)["title"] == "My Page"

    def test_no_title_without_text_mode(self, monkeypatch):
        assert self._fetch(monkeypatch, self.PAGE)["title"] is None

    def test_no_title_for_non_html(self, monkeypatch):
        result = self._fetch(monkeypatch, "<title>not a page</title>",
                             headers={"Content-Type": "text/plain"}, as_text=True)
        assert result["title"] is None

    def test_title_in_report(self):
        result = {"url": "https://example.com", "final_url": "https://example.com",
                  "status_code": 200, "content_type": "text/html", "title": "My Page",
                  "length": 5, "truncated": False, "text_extracted": True, "content": "Body."}
        assert "Title: My Page" in uc.format_result(result)
        assert "Title:" not in uc.format_result({**result, "title": None})


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


class TestRespectRobots:
    def _result(self, url, final_url=None):
        return {
            "url": url, "final_url": final_url or url, "status_code": 200,
            "content_type": "text/html", "title": None, "length": 2,
            "truncated": False, "text_extracted": True, "content": "hi",
        }

    def _wire(self, monkeypatch, refusals=None, final_url=None):
        checked, fetched = [], []

        def fake_refusal(url, timeout):
            checked.append(url)
            return (refusals or {}).get(url)

        def fake_fetch(url, timeout, max_chars, as_text):
            fetched.append(url)
            return self._result(url, final_url)

        monkeypatch.setattr(uc, "robots_refusal", fake_refusal)
        monkeypatch.setattr(uc, "fetch_content", fake_fetch)
        return checked, fetched

    def test_flag_parsed(self):
        assert uc.parse_args(["https://x.com"]).respect_robots is False
        assert uc.parse_args(["https://x.com", "--respect-robots"]).respect_robots is True

    def test_off_by_default_never_checks(self, monkeypatch, capsys):
        checked, fetched = self._wire(monkeypatch)
        uc.main(["https://x.com/a", "--json"])
        assert checked == []
        assert fetched == ["https://x.com/a"]
        assert json.loads(capsys.readouterr().out)["robots_checked"] is False

    def test_allowed_page_fetched_and_flagged(self, monkeypatch, capsys):
        checked, fetched = self._wire(monkeypatch)
        uc.main(["https://x.com/a", "--respect-robots", "--json"])
        assert checked == ["https://x.com/a"]
        assert fetched == ["https://x.com/a"]
        assert json.loads(capsys.readouterr().out)["robots_checked"] is True

    def test_refused_page_never_fetched(self, monkeypatch, capsys):
        reason = "x.com's robots.txt disallows /a for online-search-url-content"
        checked, fetched = self._wire(monkeypatch, refusals={"https://x.com/a": reason})
        with pytest.raises(SystemExit) as exc:
            uc.main(["https://x.com/a", "--respect-robots", "--json"])
        assert exc.value.code == 1
        assert fetched == []
        assert json.loads(capsys.readouterr().err) == {"error": f"blocked: {reason}"}

    def test_refused_text_mode(self, monkeypatch, capsys):
        self._wire(monkeypatch, refusals={"https://x.com/a": "nope"})
        with pytest.raises(SystemExit):
            uc.main(["https://x.com/a", "--respect-robots"])
        assert capsys.readouterr().err.strip() == "Error: blocked: nope"

    def test_redirect_target_checked_and_refused(self, monkeypatch, capsys):
        checked, _ = self._wire(
            monkeypatch, final_url="https://y.com/b",
            refusals={"https://y.com/b": "y.com's robots.txt opts out of AI input"},
        )
        with pytest.raises(SystemExit) as exc:
            uc.main(["https://x.com/a", "--respect-robots", "--json"])
        assert exc.value.code == 1
        assert checked == ["https://x.com/a", "https://y.com/b"]
        captured = capsys.readouterr()
        assert captured.out == ""  # the redirected page's content is discarded
        assert json.loads(captured.err)["error"].startswith(
            "blocked after redirect to https://y.com/b:")

    def test_redirect_target_allowed(self, monkeypatch, capsys):
        checked, _ = self._wire(monkeypatch, final_url="https://y.com/b")
        uc.main(["https://x.com/a", "--respect-robots", "--json"])
        assert checked == ["https://x.com/a", "https://y.com/b"]
        assert json.loads(capsys.readouterr().out)["final_url"] == "https://y.com/b"

    def test_fragment_only_difference_not_rechecked(self, monkeypatch):
        checked, _ = self._wire(monkeypatch, final_url="https://x.com/a")
        uc.main(["https://x.com/a#top", "--respect-robots", "--json"])
        assert checked == ["https://x.com/a#top"]

    def test_robots_refusal_uses_script_identity(self, monkeypatch):
        seen = []
        monkeypatch.setattr(uc.robots, "check",
                            lambda url, ua, token, timeout: seen.append((url, ua, token, timeout)))
        uc.robots_refusal("https://x.com/a", 7)
        assert seen == [("https://x.com/a", uc.USER_AGENT, "online-search-url-content", 7)]


class TestWarnRobots:
    def _wire(self, monkeypatch, ai_input=None, disallowed=None, final_url=None):
        noted, refused = [], []

        def fake_fetch(url, timeout, max_chars, as_text):
            return {
                "url": url, "final_url": final_url or url, "status_code": 200,
                "content_type": "text/html", "title": "T", "length": 2,
                "truncated": False, "text_extracted": True, "content": "hi",
            }

        def fake_notes(url, timeout):
            noted.append(url)
            return {"ai_input": ai_input, "disallowed": disallowed}

        monkeypatch.setattr(uc, "fetch_content", fake_fetch)
        monkeypatch.setattr(uc, "robots_notes", fake_notes)
        monkeypatch.setattr(uc, "robots_refusal", lambda url, timeout: refused.append(url))
        return noted, refused

    def test_flag_parsed(self):
        assert uc.parse_args(["https://x.com"]).warn_robots is False
        assert uc.parse_args(["https://x.com", "--warn-robots"]).warn_robots is True

    def test_cannot_combine_with_respect_robots(self):
        with pytest.raises(SystemExit) as exc:
            uc.parse_args(["https://x.com", "--warn-robots", "--respect-robots"])
        assert exc.value.code == 2

    def test_notes_reported_and_page_still_returned(self, monkeypatch, capsys):
        noted, refused = self._wire(monkeypatch, ai_input="opt-out reason",
                                    disallowed="disallow reason")
        uc.main(["https://x.com/a", "--warn-robots", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["content"] == "hi"
        assert payload["ai_input_warning"] == "opt-out reason"
        assert payload["robots_disallow_note"] == "disallow reason"
        assert payload["robots_checked"] is True
        assert noted == ["https://x.com/a"]
        assert refused == []  # never the refusing check

    def test_no_notes_are_null(self, monkeypatch, capsys):
        self._wire(monkeypatch)
        uc.main(["https://x.com/a", "--warn-robots", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["ai_input_warning"] is None
        assert payload["robots_disallow_note"] is None

    def test_checks_the_page_after_redirects(self, monkeypatch, capsys):
        noted, _ = self._wire(monkeypatch, final_url="https://y.com/b")
        uc.main(["https://x.com/a", "--warn-robots", "--json"])
        assert noted == ["https://y.com/b"]

    def test_not_checked_without_flag(self, monkeypatch, capsys):
        noted, _ = self._wire(monkeypatch, ai_input="should not appear", disallowed="nor this")
        uc.main(["https://x.com/a", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert noted == []
        assert payload["ai_input_warning"] is None
        assert payload["robots_disallow_note"] is None
        assert payload["robots_checked"] is False

    def test_text_report_shows_both(self, monkeypatch, capsys):
        self._wire(monkeypatch, ai_input="x.com's robots.txt opts out of AI input",
                   disallowed="x.com's robots.txt asks automated clients not to fetch /a")
        uc.main(["https://x.com/a", "--warn-robots"])
        out = capsys.readouterr().out
        assert "Warning: x.com's robots.txt opts out of AI input" in out
        assert "Note: x.com's robots.txt asks automated clients not to fetch /a" in out

    def test_respect_robots_reports_null_notes(self, monkeypatch, capsys):
        noted, _ = self._wire(monkeypatch)
        monkeypatch.setattr(uc, "robots_refusal", lambda url, timeout: None)
        uc.main(["https://x.com/a", "--respect-robots", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["robots_checked"] is True
        # A page with either problem would have been refused outright.
        assert payload["ai_input_warning"] is None
        assert payload["robots_disallow_note"] is None
        assert noted == []

    def test_robots_notes_uses_script_identity(self, monkeypatch):
        seen = []
        monkeypatch.setattr(uc.robots, "review",
                            lambda url, ua, token, timeout: seen.append((url, ua, token, timeout)))
        uc.robots_notes("https://x.com/a", 7)
        assert seen == [("https://x.com/a", uc.USER_AGENT, "online-search-url-content", 7)]
