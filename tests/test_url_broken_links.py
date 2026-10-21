"""Tests for url_broken_links: link selection, robots and throttle handling,
classification, Wayback lookups, the report, and main() output/exit paths."""

import argparse
import json

import pytest
import requests

import url_availability
import url_broken_links as ubl
import url_links

PAGE = "https://example.com/docs/"


def _link(url, text="t"):
    return {"text": text, "url": url}


def _checked(url, status_code=200, final_url=None, reason="OK"):
    return {"url": url, "available": status_code < 400, "status_code": status_code,
            "reason": reason, "final_url": final_url or url, "elapsed_ms": 5}


class FakeThrottle:
    def __init__(self):
        self.hosts = []

    def wait(self, host):
        self.hosts.append(host)


class FakeRobots:
    """RobotsCache stand-in: {host: (robots.txt text, problem)}."""

    def __init__(self, files=None):
        self.files = files or {}
        self.calls = []

    def get(self, url):
        host = ubl.host_of(url)
        self.calls.append(host)
        text, problem = self.files.get(host, ("", None))
        groups, signals = ubl.robots.parse(text) if problem is None else ([], [])
        return groups, signals, problem


class TestNonNegativeFloat:
    @pytest.mark.parametrize("value, expected", [("0", 0.0), ("1.5", 1.5)])
    def test_accepts(self, value, expected):
        assert ubl.non_negative_float(value) == expected

    @pytest.mark.parametrize("value", ["-1", "abc"])
    def test_rejects(self, value):
        with pytest.raises(argparse.ArgumentTypeError):
            ubl.non_negative_float(value)


class TestHostThrottle:
    def test_waits_only_for_the_same_host(self, monkeypatch):
        now = [100.0]
        sleeps = []
        monkeypatch.setattr(ubl.time, "monotonic", lambda: now[0])
        monkeypatch.setattr(ubl.time, "sleep", sleeps.append)
        throttle = ubl.HostThrottle(1.0)
        throttle.wait("a.com")
        throttle.wait("b.com")
        now[0] = 100.25
        throttle.wait("a.com")
        assert sleeps == [pytest.approx(0.75)]

    def test_no_wait_after_the_gap(self, monkeypatch):
        now = [100.0]
        sleeps = []
        monkeypatch.setattr(ubl.time, "monotonic", lambda: now[0])
        monkeypatch.setattr(ubl.time, "sleep", sleeps.append)
        throttle = ubl.HostThrottle(1.0)
        throttle.wait("a.com")
        now[0] = 102.0
        throttle.wait("a.com")
        assert sleeps == []


class TestRobotsCache:
    def test_fetches_each_host_once_through_the_throttle(self, monkeypatch):
        fetched = []

        def fake_fetch(url, user_agent, timeout):
            fetched.append((url, user_agent))
            return "User-agent: *\nDisallow: /private\n", None

        monkeypatch.setattr(ubl.robots, "fetch", fake_fetch)
        throttle = FakeThrottle()
        cache = ubl.RobotsCache(throttle, 5)
        groups, _, problem = cache.get("https://a.com/x")
        cache.get("https://A.com/y")
        assert len(fetched) == 1 and fetched[0][1] == ubl.USER_AGENT
        assert throttle.hosts == ["a.com"] and problem is None
        assert not ubl.robots.is_allowed(groups, ubl.ROBOTS_TOKEN, "/private")

    def test_problem_kept(self, monkeypatch):
        monkeypatch.setattr(ubl.robots, "fetch", lambda *a, **k: (None, "boom"))
        assert ubl.RobotsCache(FakeThrottle(), 5).get("https://a.com/") == ([], [], "boom")


class TestSelectLinks:
    def test_filters_and_counts(self):
        links = [
            _link("mailto:me@example.com"),
            _link(PAGE + "#intro"),
            _link("https://example.com/a#x", "A"),
            _link("https://example.com/a#y"),
            _link("https://other.org/b", "B"),
            _link("javascript:void(0)"),
        ]
        selected, skipped = ubl.select_links(links, PAGE, "all", 100)
        assert selected == [
            {"url": "https://example.com/a", "text": "A", "internal": True},
            {"url": "https://other.org/b", "text": "B", "internal": False},
        ]
        assert skipped == {"non_http": 2, "same_page": 1, "duplicates": 1,
                           "out_of_scope": 0, "over_cap": 0}

    @pytest.mark.parametrize("scope, kept", [("internal", "https://example.com/a"),
                                             ("external", "https://other.org/b")])
    def test_scope(self, scope, kept):
        links = [_link("https://example.com/a"), _link("https://other.org/b")]
        selected, skipped = ubl.select_links(links, PAGE, scope, 100)
        assert [s["url"] for s in selected] == [kept]
        assert skipped["out_of_scope"] == 1

    def test_cap_keeps_page_order(self):
        links = [_link(f"https://x.org/{i}") for i in range(5)]
        selected, skipped = ubl.select_links(links, PAGE, "all", 2)
        assert [s["url"] for s in selected] == ["https://x.org/0", "https://x.org/1"]
        assert skipped["over_cap"] == 3


class TestClassify:
    @pytest.mark.parametrize("code, final, expected", [
        (200, "https://a.com/x", "ok"),
        (200, "https://a.com/y", "redirected"),
        (404, "https://a.com/x", "broken"),
        (500, "https://a.com/x", "broken"),
        (403, "https://a.com/x", "blocked"),
        (401, "https://a.com/x", "blocked"),
        (429, "https://a.com/x", "blocked"),
    ])
    def test_matrix(self, code, final, expected):
        assert ubl.classify(code, "https://a.com/x", final) == expected


class TestLandsOnHomePage:
    @pytest.mark.parametrize("url, final, expected", [
        ("http://a.com/paper.pdf", "https://parked.com", True),
        ("http://a.com/paper.pdf", "https://parked.com/", True),
        ("http://a.com/paper.pdf", "https://a.com/new/paper.pdf", False),
        ("http://a.com/", "https://a.com/", False),
        ("http://a.com/p", "https://a.com/?lang=en", False),
    ])
    def test_matrix(self, url, final, expected):
        assert ubl.lands_on_home_page(url, final) is expected


class TestCheckLink:
    LINK = {"url": "https://a.com/page", "text": "Page", "internal": False}

    def _check(self, monkeypatch, robots_files=None, response=None, error=None):
        calls = []

        def fake_check(url, timeout, user_agent):
            calls.append((url, timeout, user_agent))
            if error:
                raise error
            return response

        monkeypatch.setattr(url_availability, "check_url", fake_check)
        throttle = FakeThrottle()
        record = ubl.check_link(self.LINK, FakeRobots(robots_files), throttle, 7)
        return record, calls, throttle

    def test_ok_with_own_user_agent(self, monkeypatch):
        record, calls, throttle = self._check(monkeypatch, response=_checked(self.LINK["url"]))
        assert record["status"] == "ok" and record["status_code"] == 200
        assert calls == [("https://a.com/page", 7, ubl.USER_AGENT)]
        assert throttle.hosts == ["a.com"]

    def test_redirect_to_home_page_noted(self, monkeypatch):
        record, _, _ = self._check(monkeypatch, response=_checked(
            self.LINK["url"], final_url="https://parked.example/"))
        assert record["status"] == "redirected" and "may be gone" in record["note"]

    def test_broken(self, monkeypatch):
        record, _, _ = self._check(monkeypatch, response=_checked(
            self.LINK["url"], 404, reason="Not Found"))
        assert (record["status"], record["reason"]) == ("broken", "Not Found")

    def test_connection_error_unreachable(self, monkeypatch):
        record, _, _ = self._check(monkeypatch, error=requests.ConnectionError("no route"))
        assert record["status"] == "unreachable" and record["error"] == "no route"

    def test_robots_disallow_skips_fetch(self, monkeypatch):
        record, calls, _ = self._check(
            monkeypatch, robots_files={"a.com": ("User-agent: *\nDisallow: /page\n", None)})
        assert record["status"] == "skipped_robots" and calls == []
        assert "disallows /page" in record["error"]

    @pytest.mark.parametrize("problem, status", [
        ("its robots.txt couldn't be fetched (ConnectionError)", "unreachable"),
        ("its robots.txt couldn't be fetched (ConnectTimeout)", "unreachable"),
        ("its robots.txt couldn't be fetched (ReadTimeout)", "skipped_robots"),
        ("its robots.txt couldn't be fetched (SSLError)", "skipped_robots"),
        ("its robots.txt returned HTTP 503", "skipped_robots"),
    ])
    def test_unreadable_robots(self, monkeypatch, problem, status):
        record, calls, _ = self._check(monkeypatch, robots_files={"a.com": (None, problem)})
        assert record["status"] == status and calls == []
        assert record["error"] == f"a.com: {problem}"


class TestAddWaybackCopies:
    def test_only_dead_links_and_stops_at_429(self, monkeypatch):
        looked_up = []

        def fake_add(record, timeout):
            looked_up.append(record["url"])
            record["archived"] = None
            record["archive_error"] = "429 Client Error: Too Many Requests"
            return record

        monkeypatch.setattr(url_availability, "add_wayback", fake_add)
        records = [{"url": "u1", "status": "ok"}, {"url": "u2", "status": "broken"},
                   {"url": "u3", "status": "unreachable"}]
        throttle = FakeThrottle()
        ubl.add_wayback_copies(records, throttle, 5)
        assert looked_up == ["u2"] and throttle.hosts == [ubl.WAYBACK_HOST]
        assert "archived" not in records[0]
        assert records[2]["archived"] is None and "rate-limited" in records[2]["archive_error"]


class TestPageNotes:
    def test_opt_out_and_disallow(self):
        robots_text = "User-agent: *\nContent-Signal: ai-input=no\nDisallow: /docs/\n"
        notes = ubl.page_notes(FakeRobots({"example.com": (robots_text, None)}), PAGE)
        assert "ai-input=no" in notes["ai_input_warning"]
        assert "/docs/" in notes["robots_disallow_note"]

    def test_unreadable_robots_no_notes(self):
        notes = ubl.page_notes(FakeRobots({"example.com": (None, "boom")}), PAGE)
        assert notes == {"ai_input_warning": None, "robots_disallow_note": None}


@pytest.fixture
def wired(monkeypatch):
    """check_page() with the page fetch, link checks and robots.txt faked."""
    monkeypatch.setattr(ubl.time, "sleep", lambda s: None)
    monkeypatch.setattr(ubl.robots, "fetch", lambda url, ua, timeout: ("", None))
    page_calls = []

    def fake_fetch_links(url, timeout, user_agent):
        page_calls.append((url, user_agent))
        links = [_link("https://example.com/ok"), _link("https://example.com/gone", "Gone"),
                 _link("https://down.example/x"), _link("mailto:a@b.c")]
        return {"url": url, "final_url": PAGE, "status_code": 200,
                "content_type": "text/html", "link_count": len(links), "links": links}

    def fake_check(url, timeout, user_agent):
        if "gone" in url:
            return _checked(url, 404, reason="Not Found")
        if "down" in url:
            raise requests.ConnectionError("DNS failure")
        return _checked(url)

    monkeypatch.setattr(url_links, "fetch_links", fake_fetch_links)
    monkeypatch.setattr(url_availability, "check_url", fake_check)
    return page_calls


class TestCheckPage:
    def test_result(self, wired):
        result = ubl.check_page("https://example.com/docs")
        assert wired == [("https://example.com/docs", ubl.USER_AGENT)]
        assert result["final_url"] == PAGE and result["checked"] == 3
        assert result["counts"] == {"ok": 1, "redirected": 0, "broken": 1, "blocked": 0,
                                    "unreachable": 1, "skipped_robots": 0}
        assert result["skipped"]["non_http"] == 1
        assert [r["status"] for r in result["links"]] == ["ok", "broken", "unreachable"]
        assert result["ai_input_warning"] is None

    def test_wayback(self, wired, monkeypatch):
        def fake_add(record, timeout):
            record["archived"] = {"url": "https://web.archive.org/x"}
            record["archive_error"] = None
            return record

        monkeypatch.setattr(url_availability, "add_wayback", fake_add)
        result = ubl.check_page("https://example.com/docs", wayback=True)
        assert [("archived" in r) for r in result["links"]] == [False, True, True]


class TestFormatResult:
    def test_sections(self, wired):
        out = ubl.format_result(ubl.check_page("https://example.com/docs"))
        assert "Redirected to: https://example.com/docs/" in out
        assert "Links found: 4; checked: 3 (left out: 1 non-web)" in out
        assert "Result: 1 ok, 0 redirected, 1 broken, 0 blocked, 1 unreachable" in out
        assert '404 Not Found  https://example.com/gone  "Gone"' in out
        assert "Unreachable (1):" in out and "DNS failure" in out
        assert "Blocked" not in out


class TestMain:
    def test_json(self, wired, capsys):
        ubl.main(["https://example.com/docs", "--json", "--max-links", "2"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["checked"] == 2 and payload["skipped"]["over_cap"] == 1

    def test_text_progress_line(self, wired, capsys):
        ubl.main(["https://example.com/docs"])
        assert capsys.readouterr().out.startswith("Checking the links on: https://example.com/docs")

    def test_page_failure_exits_1(self, monkeypatch, capsys):
        def boom(url, timeout, user_agent):
            raise requests.HTTPError("404 Client Error")

        monkeypatch.setattr(url_links, "fetch_links", boom)
        with pytest.raises(SystemExit) as exc:
            ubl.main(["https://example.com/missing", "--json"])
        assert exc.value.code == 1
        assert "couldn't fetch the page: 404" in json.loads(capsys.readouterr().err)["error"]

    def test_missing_bs4_exits_1(self, monkeypatch, capsys):
        def no_bs4(url, timeout, user_agent):
            raise ImportError("bs4")

        monkeypatch.setattr(url_links, "fetch_links", no_bs4)
        with pytest.raises(SystemExit) as exc:
            ubl.main(["https://example.com/"])
        assert exc.value.code == 1 and "beautifulsoup4" in capsys.readouterr().err

    def test_bad_scheme_exits_1(self, capsys):
        with pytest.raises(SystemExit) as exc:
            ubl.main(["example.com", "--json"])
        assert exc.value.code == 1

    @pytest.mark.parametrize("args", [["--max-links", "0"], ["--max-links", "1001"],
                                      ["--delay", "-1"], ["--scope", "nope"]])
    def test_bad_options_exit_2(self, args):
        with pytest.raises(SystemExit) as exc:
            ubl.main(["https://example.com/", *args])
        assert exc.value.code == 2
