"""Tests for url_availability: GET request, status classification, and main()."""

import json

import pytest
import requests

import url_availability as ua
from helpers import FakeResponse


class TestCheckUrl:
    def test_available_on_200(self, monkeypatch):
        response = FakeResponse(status_code=200, reason="OK", url="https://example.com/")

        def fake_get(url, **kwargs):
            assert url == "https://example.com"
            assert kwargs["timeout"] == ua.TIMEOUT_SECONDS
            assert kwargs["allow_redirects"] is True
            return response

        monkeypatch.setattr(ua.requests, "get", fake_get)
        result = ua.check_url("https://example.com")
        assert result["available"] is True
        assert result["status_code"] == 200
        assert result["reason"] == "OK"
        assert result["final_url"] == "https://example.com/"
        assert result["elapsed_ms"] >= 0

    def test_unavailable_on_404(self, monkeypatch):
        response = FakeResponse(status_code=404, reason="Not Found", url="https://example.com/x")
        monkeypatch.setattr(ua.requests, "get", lambda url, **kwargs: response)
        result = ua.check_url("https://example.com/x")
        assert result["available"] is False
        assert result["status_code"] == 404

    def test_unavailable_on_500(self, monkeypatch):
        response = FakeResponse(status_code=500, reason="Server Error", url="https://example.com")
        monkeypatch.setattr(ua.requests, "get", lambda url, **kwargs: response)
        result = ua.check_url("https://example.com")
        assert result["available"] is False

    def test_custom_timeout_passed_through(self, monkeypatch):
        captured = {}

        def fake_get(url, **kwargs):
            captured.update(kwargs)
            return FakeResponse(status_code=200, url=url)

        monkeypatch.setattr(ua.requests, "get", fake_get)
        ua.check_url("https://example.com", timeout=3)
        assert captured["timeout"] == 3

    def test_connection_error_propagates(self, monkeypatch):
        def fake_get(url, **kwargs):
            raise requests.ConnectionError("boom")

        monkeypatch.setattr(ua.requests, "get", fake_get)
        with pytest.raises(requests.ConnectionError):
            ua.check_url("https://example.com")


class TestFormatResult:
    def test_no_redirect(self):
        result = {
            "url": "https://example.com",
            "final_url": "https://example.com",
            "available": True,
            "status_code": 200,
            "reason": "OK",
            "elapsed_ms": 42,
        }
        out = ua.format_result(result)
        assert "Redirected to:" not in out
        assert "AVAILABLE (200 OK)" in out
        assert "42 ms" in out

    def test_redirect_shown(self):
        result = {
            "url": "http://example.com",
            "final_url": "https://example.com/",
            "available": True,
            "status_code": 200,
            "reason": "OK",
            "elapsed_ms": 10,
        }
        out = ua.format_result(result)
        assert "Redirected to: https://example.com/" in out

    def test_not_available_label(self):
        result = {
            "url": "https://example.com",
            "final_url": "https://example.com",
            "available": False,
            "status_code": 404,
            "reason": "Not Found",
            "elapsed_ms": 5,
        }
        assert "NOT AVAILABLE (404 Not Found)" in ua.format_result(result)


class TestParseArgs:
    def test_defaults(self):
        args = ua.parse_args(["https://example.com"])
        assert args.url == "https://example.com"
        assert args.timeout == ua.TIMEOUT_SECONDS
        assert args.json is False

    def test_flags(self):
        args = ua.parse_args(["https://example.com", "--timeout", "5", "--json"])
        assert args.timeout == 5
        assert args.json is True

    def test_invalid_timeout_rejected(self):
        with pytest.raises(SystemExit) as exc:
            ua.parse_args(["https://example.com", "--timeout", "0"])
        assert exc.value.code == 2


class TestMain:
    def test_rejects_missing_scheme_json(self, capsys):
        with pytest.raises(SystemExit) as exc:
            ua.main(["example.com", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "URL must start with http:// or https://, got: example.com"
        }

    def test_rejects_missing_scheme_text(self, capsys):
        with pytest.raises(SystemExit):
            ua.main(["example.com"])
        assert "must start with http" in capsys.readouterr().err

    def test_request_error_exits_json(self, monkeypatch, capsys):
        def boom(url, timeout):
            raise requests.ConnectionError("Name or service not known")

        monkeypatch.setattr(ua, "check_url", boom)
        with pytest.raises(SystemExit) as exc:
            ua.main(["https://nosuchhost.invalid", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "Name or service not known"
        }

    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            ua,
            "check_url",
            lambda url, timeout: {
                "url": url,
                "available": True,
                "status_code": 200,
                "reason": "OK",
                "final_url": url,
                "elapsed_ms": 12,
            },
        )
        ua.main(["https://example.com", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["available"] is True
        assert payload["status_code"] == 200

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            ua,
            "check_url",
            lambda url, timeout: {
                "url": url,
                "available": False,
                "status_code": 404,
                "reason": "Not Found",
                "final_url": url,
                "elapsed_ms": 7,
            },
        )
        ua.main(["https://example.com/missing"])
        out = capsys.readouterr().out
        assert "Checking: https://example.com/missing" in out
        assert "NOT AVAILABLE (404 Not Found)" in out
