"""Tests for url_availability: GET request, status classification, Wayback lookup, and main()."""

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

    def test_user_agent(self, monkeypatch):
        captured = []

        def fake_get(url, **kwargs):
            captured.append(kwargs["headers"]["User-Agent"])
            return FakeResponse(status_code=200, reason="OK", url=url)

        monkeypatch.setattr(ua.requests, "get", fake_get)
        ua.check_url("https://example.com")
        ua.check_url("https://example.com", user_agent="custom/1.0")
        assert captured == [ua.USER_AGENT, "custom/1.0"]

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


SNAPSHOT_JSON = {
    "url": "https://example.com/gone",
    "archived_snapshots": {
        "closest": {
            "status": "200",
            "available": True,
            "url": "http://web.archive.org/web/20240312094501/https://example.com/gone",
            "timestamp": "20240312094501",
        }
    },
}


def dead_result(**extra):
    result = {
        "url": "https://example.com/gone",
        "final_url": "https://example.com/gone",
        "available": False,
        "status_code": 404,
        "reason": "Not Found",
        "elapsed_ms": 5,
    }
    result.update(extra)
    return result


class TestFetchWayback:
    def test_snapshot_found(self, monkeypatch):
        def fake_get(url, **kwargs):
            assert url == ua.WAYBACK_API_URL
            assert kwargs["params"] == {"url": "https://example.com/gone"}
            assert kwargs["timeout"] == 7
            return FakeResponse(json_data=SNAPSHOT_JSON)

        monkeypatch.setattr(ua.requests, "get", fake_get)
        assert ua.fetch_wayback("https://example.com/gone", timeout=7) == {
            "url": "http://web.archive.org/web/20240312094501/https://example.com/gone",
            "timestamp": "20240312094501",
            "archived_at": "2024-03-12T09:45:01Z",
            "status": 200,
        }

    def test_no_snapshot(self, monkeypatch):
        response = FakeResponse(json_data={"url": "x", "archived_snapshots": {}})
        monkeypatch.setattr(ua.requests, "get", lambda url, **kwargs: response)
        assert ua.fetch_wayback("https://example.com/gone") is None

    def test_snapshot_marked_unavailable(self, monkeypatch):
        data = {"archived_snapshots": {"closest": {"available": False, "url": "u"}}}
        monkeypatch.setattr(
            ua.requests, "get", lambda url, **kwargs: FakeResponse(json_data=data)
        )
        assert ua.fetch_wayback("https://example.com/gone") is None

    def test_odd_timestamp_and_status_kept_raw(self, monkeypatch):
        data = {
            "archived_snapshots": {
                "closest": {"available": True, "url": "u", "timestamp": "2024", "status": "-"}
            }
        }
        monkeypatch.setattr(
            ua.requests, "get", lambda url, **kwargs: FakeResponse(json_data=data)
        )
        snapshot = ua.fetch_wayback("https://example.com/gone")
        assert snapshot["timestamp"] == "2024"
        assert snapshot["archived_at"] is None
        assert snapshot["status"] == "-"

    def test_rate_limit_raises(self, monkeypatch):
        response = FakeResponse(
            status_code=429,
            raise_for_status=requests.HTTPError("429 Client Error: Too Many Requests"),
        )
        monkeypatch.setattr(ua.requests, "get", lambda url, **kwargs: response)
        with pytest.raises(requests.HTTPError):
            ua.fetch_wayback("https://example.com/gone")

    def test_non_json_body_raises(self, monkeypatch):
        response = FakeResponse(text="<html>busy</html>")
        monkeypatch.setattr(ua.requests, "get", lambda url, **kwargs: response)
        with pytest.raises(ValueError):
            ua.fetch_wayback("https://example.com/gone")


class TestAddWayback:
    def test_snapshot_added(self, monkeypatch):
        monkeypatch.setattr(ua, "fetch_wayback", lambda url, timeout: {"url": "snap"})
        result = ua.add_wayback(dead_result())
        assert result["archived"] == {"url": "snap"}
        assert result["archive_error"] is None

    def test_request_failure_recorded(self, monkeypatch):
        def boom(url, timeout):
            raise requests.HTTPError("429 Client Error: Too Many Requests")

        monkeypatch.setattr(ua, "fetch_wayback", boom)
        result = ua.add_wayback(dead_result())
        assert result["archived"] is None
        assert result["archive_error"] == "429 Client Error: Too Many Requests"

    def test_empty_error_message_named(self, monkeypatch):
        def boom(url, timeout):
            raise ValueError()

        monkeypatch.setattr(ua, "fetch_wayback", boom)
        assert ua.add_wayback(dead_result())["archive_error"] == "ValueError"


class TestUnreachableResult:
    def test_shape(self):
        result = ua.unreachable_result("https://x.invalid", requests.ConnectionError("dns"))
        assert result == {
            "url": "https://x.invalid",
            "available": False,
            "status_code": None,
            "reason": None,
            "final_url": None,
            "elapsed_ms": None,
            "error": "dns",
        }


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

    def test_no_archive_line_without_lookup(self):
        assert "Archived copy" not in ua.format_result(dead_result())

    def test_archived_copy_shown(self):
        snapshot = {
            "url": "http://web.archive.org/web/20240312094501/https://example.com/gone",
            "timestamp": "20240312094501",
            "archived_at": "2024-03-12T09:45:01Z",
            "status": 200,
        }
        out = ua.format_result(dead_result(archived=snapshot, archive_error=None))
        assert f"Archived copy: {snapshot['url']}" in out
        assert "Archived 2024-03-12 09:45:01 UTC; page status then: 200" in out

    def test_raw_timestamp_when_unparsed(self):
        snapshot = {"url": "u", "timestamp": "2024", "archived_at": None, "status": "-"}
        out = ua.format_result(dead_result(archived=snapshot, archive_error=None))
        assert "Archived 2024; page status then: -" in out

    def test_no_archived_copy(self):
        out = ua.format_result(dead_result(archived=None, archive_error=None))
        assert "Archived copy: none found in the Wayback Machine" in out

    def test_lookup_failed(self):
        out = ua.format_result(dead_result(archived=None, archive_error="429 Too Many"))
        assert "Archived copy: lookup failed (429 Too Many)" in out

    def test_unreachable(self):
        out = ua.format_result(ua.unreachable_result("https://x.invalid", "dns failure"))
        assert "Status: NOT REACHABLE (dns failure)" in out
        assert "Response time" not in out
        assert "Redirected" not in out


class TestParseArgs:
    def test_defaults(self):
        args = ua.parse_args(["https://example.com"])
        assert args.url == "https://example.com"
        assert args.timeout == ua.TIMEOUT_SECONDS
        assert args.json is False
        assert args.wayback is False

    def test_flags(self):
        args = ua.parse_args(
            ["https://example.com", "--timeout", "5", "--json", "--wayback"]
        )
        assert args.timeout == 5
        assert args.json is True
        assert args.wayback is True

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


class TestMainWayback:
    @staticmethod
    def _no_lookup(url, timeout):
        raise AssertionError("Wayback lookup should not run")

    def test_dead_page_gets_archive_fields(self, monkeypatch, capsys):
        captured = {}

        def fake_fetch(url, timeout):
            captured.update(url=url, timeout=timeout)
            return {"url": "snap", "timestamp": "t", "archived_at": None, "status": 200}

        monkeypatch.setattr(ua, "check_url", lambda url, timeout: dead_result(url=url))
        monkeypatch.setattr(ua, "fetch_wayback", fake_fetch)
        ua.main(["https://example.com/gone", "--wayback", "--timeout", "4", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["archived"]["url"] == "snap"
        assert payload["archive_error"] is None
        assert captured == {"url": "https://example.com/gone", "timeout": 4}

    def test_available_page_skips_lookup(self, monkeypatch, capsys):
        monkeypatch.setattr(
            ua,
            "check_url",
            lambda url, timeout: dead_result(url=url, available=True, status_code=200),
        )
        monkeypatch.setattr(ua, "fetch_wayback", self._no_lookup)
        ua.main(["https://example.com/gone", "--wayback", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert "archived" not in payload
        assert "archive_error" not in payload

    def test_dead_page_without_flag_skips_lookup(self, monkeypatch, capsys):
        monkeypatch.setattr(ua, "check_url", lambda url, timeout: dead_result(url=url))
        monkeypatch.setattr(ua, "fetch_wayback", self._no_lookup)
        ua.main(["https://example.com/gone", "--json"])
        assert "archived" not in json.loads(capsys.readouterr().out)

    def test_connection_error_reported_not_exited(self, monkeypatch, capsys):
        def boom(url, timeout):
            raise requests.ConnectionError("Name or service not known")

        monkeypatch.setattr(ua, "check_url", boom)
        monkeypatch.setattr(ua, "fetch_wayback", lambda url, timeout: None)
        ua.main(["https://nosuchhost.invalid", "--wayback", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["available"] is False
        assert payload["status_code"] is None
        assert payload["error"] == "Name or service not known"
        assert payload["archived"] is None
        assert payload["archive_error"] is None

    def test_lookup_failure_still_exits_zero_text(self, monkeypatch, capsys):
        def boom(url, timeout):
            raise requests.HTTPError("429 Client Error: Too Many Requests")

        monkeypatch.setattr(ua, "check_url", lambda url, timeout: dead_result(url=url))
        monkeypatch.setattr(ua, "fetch_wayback", boom)
        ua.main(["https://example.com/gone", "--wayback"])
        out = capsys.readouterr().out
        assert "NOT AVAILABLE (404 Not Found)" in out
        assert "Archived copy: lookup failed (429 Client Error: Too Many Requests)" in out
