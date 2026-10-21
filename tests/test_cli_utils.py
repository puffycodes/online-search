"""Tests for cli_utils: dotenv loading, result formatting/printing, the
die() error-exit helper, require_env, redact() and the HTTP-error helpers, URL-scheme validation, response_text() decoding, the
positive_int / non_negative_int / bounded_int argparse types, and UTF-8 output."""

import argparse
import io
import json
import os
import sys

import pytest
import requests

from cli_utils import (
    bounded_int,
    die,
    format_result,
    http_error_detail,
    load_dotenv,
    non_negative_int,
    positive_int,
    print_results,
    raise_for_status,
    redact,
    require_env,
    response_text,
    use_utf8_output,
    validate_url_scheme,
)
from helpers import FakeResponse


class TestRedact:
    def test_replaces_every_occurrence(self):
        assert redact("a=KEY&b=KEY", "KEY") == "a=<redacted>&b=<redacted>"

    @pytest.mark.parametrize("secret", ["", None])
    def test_no_secret_leaves_message(self, secret):
        assert redact("message", secret) == "message"


class TestHttpErrorDetail:
    @pytest.mark.parametrize("body, expected", [
        ({"error": {"code": "SUBSCRIPTION_TOKEN_INVALID",
                    "detail": "The provided subscription token is invalid.", "status": 422}},
         "SUBSCRIPTION_TOKEN_INVALID: The provided subscription token is invalid."),
        ({"error": "Invalid API key."}, "Invalid API key."),
        ({"message": "Unauthorized"}, "Unauthorized"),
        ({"detail": {"error": "Rate limit"}}, None),
        ({"detail": "Too many requests"}, "Too many requests"),
        ({"detail": [{"msg": "field required"}, {"msg": "bad value"}]}, "field required; bad value"),
        ({"error": {"code": "X", "message": "X"}}, "X"),
        ({"results": []}, None),
    ])
    def test_json_bodies(self, body, expected):
        response = FakeResponse(json_data=body, text="")
        assert http_error_detail(response) == expected

    def test_plain_text_body(self):
        assert http_error_detail(FakeResponse(text="quota exceeded")) == "quota exceeded"

    def test_html_body_ignored(self):
        assert http_error_detail(FakeResponse(text="<html>error</html>")) is None


class TestRaiseForStatus:
    def test_ok_response_passes(self):
        raise_for_status(FakeResponse(json_data={}))

    def test_reason_added(self):
        response = FakeResponse(
            status_code=422, json_data={"error": {"code": "TOKEN_INVALID", "detail": "Bad token."}},
            raise_for_status=requests.HTTPError("422 Client Error:  for url: https://x"),
        )
        with pytest.raises(requests.HTTPError) as exc:
            raise_for_status(response)
        assert str(exc.value) == "HTTP 422: TOKEN_INVALID: Bad token."
        assert exc.value.response is response

    def test_no_reason_keeps_original_error(self):
        original = requests.HTTPError("500 Server Error")
        response = FakeResponse(status_code=500, raise_for_status=original)
        with pytest.raises(requests.HTTPError) as exc:
            raise_for_status(response)
        assert exc.value is original


class TestLoadDotenv:
    def test_missing_file_is_silently_ignored(self, tmp_path):
        load_dotenv(path=str(tmp_path / "nope.env"))

    def test_populates_environ(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLI_UTILS_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("CLI_UTILS_TEST_KEY=abc123\n# a comment\n\nBAD_LINE_NO_EQUALS\n")
        load_dotenv(path=str(env_file))
        assert os.environ["CLI_UTILS_TEST_KEY"] == "abc123"

    def test_quoted_value_is_unquoted(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLI_UTILS_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text('CLI_UTILS_TEST_KEY="quoted value"\n')
        load_dotenv(path=str(env_file))
        assert os.environ["CLI_UTILS_TEST_KEY"] == "quoted value"

    def test_real_env_var_takes_precedence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLI_UTILS_TEST_KEY", "real")
        env_file = tmp_path / ".env"
        env_file.write_text("CLI_UTILS_TEST_KEY=fromfile\n")
        load_dotenv(path=str(env_file))
        assert os.environ["CLI_UTILS_TEST_KEY"] == "real"


class TestFormatResult:
    def test_formats_three_lines(self):
        row = {"rank": 1, "title": "T", "url": "U", "snippet": "S"}
        assert format_result(row) == "1. T\n   U\n   S"


class TestPrintResults:
    def test_json_mode_prints_array(self, capsys):
        rows = [{"rank": 1, "title": "T", "url": "U", "snippet": "S"}]
        print_results(rows, True)
        assert json.loads(capsys.readouterr().out) == rows

    def test_text_mode_no_results(self, capsys):
        print_results([], False)
        assert capsys.readouterr().out.strip() == "No results found."

    def test_text_mode_formats_each_row(self, capsys):
        rows = [
            {"rank": 1, "title": "A", "url": "u1", "snippet": "s1"},
            {"rank": 2, "title": "B", "url": "u2", "snippet": "s2"},
        ]
        print_results(rows, False)
        out = capsys.readouterr().out
        assert "1. A" in out
        assert "2. B" in out
        assert out.index("1. A") < out.index("2. B")


class TestPositiveInt:
    @pytest.mark.parametrize("raw,expected", [("1", 1), ("10", 10), ("999", 999)])
    def test_accepts_positive(self, raw, expected):
        assert positive_int(raw) == expected

    @pytest.mark.parametrize("raw", ["0", "-1", "-999"])
    def test_rejects_non_positive(self, raw):
        with pytest.raises(argparse.ArgumentTypeError, match="positive integer"):
            positive_int(raw)

    @pytest.mark.parametrize("raw", ["abc", "1.5", "", "  ", "3x"])
    def test_rejects_non_integer(self, raw):
        with pytest.raises(argparse.ArgumentTypeError, match="expected an integer"):
            positive_int(raw)



class TestNonNegativeInt:
    @pytest.mark.parametrize("raw,expected", [("0", 0), ("1", 1), ("600", 600)])
    def test_accepts(self, raw, expected):
        assert non_negative_int(raw) == expected

    def test_rejects_negative(self):
        with pytest.raises(argparse.ArgumentTypeError, match="0 or greater"):
            non_negative_int("-1")

    @pytest.mark.parametrize("raw", ["abc", "1.5", ""])
    def test_rejects_non_integer(self, raw):
        with pytest.raises(argparse.ArgumentTypeError, match="expected an integer"):
            non_negative_int(raw)


class TestBoundedInt:
    @pytest.mark.parametrize("raw,expected", [("1", 1), ("10", 10)])
    def test_accepts_within_range(self, raw, expected):
        assert bounded_int(10)(raw) == expected

    def test_rejects_above_maximum(self):
        with pytest.raises(argparse.ArgumentTypeError, match="at most 10, got 11"):
            bounded_int(10)("11")

    @pytest.mark.parametrize("raw,match", [("0", "positive integer"), ("x", "expected an integer")])
    def test_rejects_like_positive_int(self, raw, match):
        with pytest.raises(argparse.ArgumentTypeError, match=match):
            bounded_int(10)(raw)

class TestRequireEnv:
    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("CLI_UTILS_TEST_KEY", "abc")
        assert require_env("CLI_UTILS_TEST_KEY", "x.py") == "abc"

    @pytest.mark.parametrize("value", [None, ""])
    def test_missing_or_empty_exits_1_plain(self, monkeypatch, capsys, value):
        if value is None:
            monkeypatch.delenv("CLI_UTILS_TEST_KEY", raising=False)
        else:
            monkeypatch.setenv("CLI_UTILS_TEST_KEY", value)
        with pytest.raises(SystemExit) as exc:
            require_env("CLI_UTILS_TEST_KEY", "web_search_x.py")
        assert exc.value.code == 1
        assert capsys.readouterr().err.strip() == (
            "Error: CLI_UTILS_TEST_KEY environment variable must be set. "
            "See the module docstring in web_search_x.py for how to obtain one."
        )

    def test_missing_exits_1_json(self, monkeypatch, capsys):
        monkeypatch.delenv("CLI_UTILS_TEST_KEY", raising=False)
        with pytest.raises(SystemExit):
            require_env("CLI_UTILS_TEST_KEY", "web_search_x.py", as_json=True)
        assert "CLI_UTILS_TEST_KEY" in json.loads(capsys.readouterr().err)["error"]


def _real_response(body, content_type):
    """A real requests.Response holding raw `body` bytes, as a server sent them."""
    import requests

    response = requests.models.Response()
    response._content = body
    response.status_code = 200
    if content_type is not None:
        response.headers["Content-Type"] = content_type
    # The encoding a live request ends up with: the header's charset, or for a
    # text/* type without one the ISO-8859-1 fallback (seen live on a
    # charset-less text/html page; get_encoding_from_headers() alone returns
    # None for it in requests 2.34).
    declared = requests.utils.get_encoding_from_headers(response.headers)
    if declared is None and (content_type or "").startswith("text/"):
        declared = "ISO-8859-1"
    response.encoding = declared
    return response


class TestResponseText:
    PAGE = "<html><head><title>Cammarata — clean</title></head><body>naïve café</body></html>"

    def test_utf8_without_charset_is_detected(self):
        # requests alone decodes this as ISO-8859-1: "\xe2\x80\x94" instead of "—".
        response = _real_response(self.PAGE.encode("utf-8"), "text/html")
        assert "\xe2\x80\x94" in response.text
        assert response_text(_real_response(self.PAGE.encode("utf-8"), "text/html")) == self.PAGE

    def test_declared_charset_is_respected(self):
        body = "café".encode("latin-1")
        assert response_text(_real_response(body, "text/html; charset=ISO-8859-1")) == "café"

    def test_declared_utf8_charset(self):
        response = _real_response(self.PAGE.encode("utf-8"), "text/html; Charset=UTF-8")
        assert response_text(response) == self.PAGE

    def test_missing_content_type(self):
        assert response_text(_real_response(self.PAGE.encode("utf-8"), None)) == self.PAGE

    def test_duck_typed_response_without_encoding_attributes(self):
        class Bare:
            text = "plain"

        assert response_text(Bare()) == "plain"


class TestValidateUrlScheme:
    @pytest.mark.parametrize("url", ["http://example.com", "https://example.com/page"])
    def test_accepts_http_and_https(self, url):
        validate_url_scheme(url)

    def test_rejects_missing_scheme_plain(self, capsys):
        with pytest.raises(SystemExit) as exc:
            validate_url_scheme("example.com")
        assert exc.value.code == 1
        assert capsys.readouterr().err.strip() == (
            "Error: URL must start with http:// or https://, got: example.com"
        )

    def test_rejects_missing_scheme_json(self, capsys):
        with pytest.raises(SystemExit) as exc:
            validate_url_scheme("example.com", as_json=True)
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "URL must start with http:// or https://, got: example.com"
        }

    def test_rejects_other_schemes(self):
        with pytest.raises(SystemExit):
            validate_url_scheme("ftp://example.com")


class TestDie:
    def test_plain_message_to_stderr_and_exit_1(self, capsys):
        with pytest.raises(SystemExit) as exc:
            die("something broke")
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.strip() == "Error: something broke"

    def test_json_message(self, capsys):
        with pytest.raises(SystemExit) as exc:
            die("bad symbol", as_json=True)
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err) == {"error": "bad symbol"}


class TestUseUtf8Output:
    def test_switches_cp1252_streams_to_utf8(self, monkeypatch):
        out_bytes, err_bytes = io.BytesIO(), io.BytesIO()
        out = io.TextIOWrapper(out_bytes, encoding="cp1252")
        err = io.TextIOWrapper(err_bytes, encoding="cp1252")
        monkeypatch.setattr(sys, "stdout", out)
        monkeypatch.setattr(sys, "stderr", err)
        use_utf8_output()
        print("25°C 東京")
        print("–", file=sys.stderr)
        out.flush()
        err.flush()
        assert out.encoding == err.encoding == "utf-8"
        assert out_bytes.getvalue().decode("utf-8").rstrip() == "25°C 東京"
        assert err_bytes.getvalue().decode("utf-8").rstrip() == "–"

    def test_leaves_streams_without_reconfigure_alone(self, monkeypatch):
        out, err = io.StringIO(), io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        monkeypatch.setattr(sys, "stderr", err)
        use_utf8_output()
        assert sys.stdout is out and sys.stderr is err

    def test_ignores_reconfigure_errors(self, monkeypatch):
        class Stubborn(io.StringIO):
            def reconfigure(self, **kwargs):
                raise ValueError("can't change encoding now")

        monkeypatch.setattr(sys, "stdout", Stubborn())
        use_utf8_output()
