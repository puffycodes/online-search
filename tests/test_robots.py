"""Tests for robots: RFC 9309 parsing and matching, Content-Signal, the robots.txt fetch, and check()."""

import pytest
import requests

import robots
from helpers import FakeResponse

TOKEN = "online-search-url-content"
UA = "Mozilla/5.0 (compatible; online-search-url-content/1.0)"


def _allowed(text, path, token=TOKEN):
    groups, _ = robots.parse(text)
    return robots.is_allowed(groups, token, path)


def _ai_ok(text, path, token=TOKEN):
    groups, global_signals = robots.parse(text)
    return robots.ai_input_allowed(groups, global_signals, token, path)


class TestParse:
    def test_groups_and_rules(self):
        groups, global_signals = robots.parse(
            "User-agent: A\nUser-agent: B\nDisallow: /x\n\nUser-agent: *\nAllow: /y\n"
        )
        assert groups == [
            {"agents": ["a", "b"], "rules": [(False, "/x")], "signals": []},
            {"agents": ["*"], "rules": [(True, "/y")], "signals": []},
        ]
        assert global_signals == []

    def test_comments_case_and_blank_disallow(self):
        groups, _ = robots.parse("USER-AGENT: *  # everyone\nDisallow:\ndisallow: /a # x\n")
        assert groups == [{"agents": ["*"], "rules": [(False, "/a")], "signals": []}]

    def test_signal_belongs_to_its_group(self):
        # Lobsters' layout: the signal follows the named crawlers' rules.
        groups, global_signals = robots.parse(
            "User-agent: GoogleBot\nAllow: /\n\nContent-Signal: ai-input=no, search=yes\n\n"
            "User-agent: *\nDisallow: /\n"
        )
        assert groups[0]["signals"] == [(None, {"ai-input": "no", "search": "yes"})]
        assert groups[1]["signals"] == []
        assert global_signals == []

    def test_signal_before_any_group_is_global(self):
        _, global_signals = robots.parse("Content-Signal: ai-train=no\nUser-agent: *\n")
        assert global_signals == [(None, {"ai-train": "no"})]

    def test_ignores_unknown_lines(self):
        groups, _ = robots.parse("Sitemap: https://x/s.xml\nnonsense\nUser-agent: *\nCrawl-delay: 5\n")
        assert groups == [{"agents": ["*"], "rules": [], "signals": []}]


class TestParseSignal:
    def test_pairs(self):
        assert robots.parse_signal("search=yes,ai-train=no , AI-Input=No") == (
            None, {"search": "yes", "ai-train": "no", "ai-input": "no"})

    def test_path_scoped(self):
        assert robots.parse_signal("/docs/ ai-input=yes") == ("/docs/", {"ai-input": "yes"})

    def test_junk_ignored(self):
        assert robots.parse_signal("hello") == (None, {})


class TestIsAllowed:
    def test_no_rules_allows(self):
        assert _allowed("", "/anything") is True

    def test_wildcard_disallow_all(self):
        assert _allowed("User-agent: *\nDisallow: /\n", "/page") is False

    def test_longest_match_wins_not_first(self):
        # urllib.robotparser would take "Allow: /" (first match) and allow this.
        text = "User-agent: *\nAllow: /\nDisallow: /search\n"
        assert _allowed(text, "/search?q=x") is False
        assert _allowed(text, "/about") is True

    def test_more_specific_allow_wins(self):
        text = "User-agent: *\nDisallow: /search\nAllow: /search/about\n"
        assert _allowed(text, "/search/about") is True
        assert _allowed(text, "/search/x") is False

    def test_allow_wins_a_tie(self):
        assert _allowed("User-agent: *\nDisallow: /p\nAllow: /p\n", "/p") is True

    def test_star_and_dollar_wildcards(self):
        text = "User-agent: *\nDisallow: /*.pdf$\nDisallow: /private*/x\n"
        assert _allowed(text, "/files/a.pdf") is False
        assert _allowed(text, "/files/a.pdf?dl=1") is True
        assert _allowed(text, "/private-area/x") is False

    def test_named_group_replaces_star(self):
        text = f"User-agent: *\nDisallow: /\n\nUser-agent: {TOKEN.upper()}\nAllow: /\n"
        assert _allowed(text, "/page") is True

    def test_other_named_group_does_not_apply(self):
        text = "User-agent: ClaudeBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        assert _allowed(text, "/page") is True

    def test_robots_txt_itself_always_allowed(self):
        assert _allowed("User-agent: *\nDisallow: /\n", "/robots.txt") is True


class TestAiInputAllowed:
    def test_no_signal_is_no_preference(self):
        assert _ai_ok("User-agent: *\nAllow: /\n", "/") is True

    def test_star_group_opt_out(self):
        assert _ai_ok("User-agent: *\nContent-Signal: ai-input=no\nAllow: /\n", "/a") is False

    def test_other_signals_ignored(self):
        assert _ai_ok("User-agent: *\nContent-Signal: search=yes, ai-train=no\n", "/a") is True

    def test_global_signal_applies(self):
        assert _ai_ok("Content-Signal: ai-input=no\nUser-agent: *\nAllow: /\n", "/a") is False

    def test_signal_in_other_group_ignored(self):
        text = "User-agent: GoogleBot\nContent-Signal: ai-input=no\n\nUser-agent: *\nAllow: /\n"
        assert _ai_ok(text, "/a") is True

    def test_path_scoped_overrides_unscoped(self):
        text = ("User-agent: *\nContent-Signal: ai-input=no\n"
                "Content-Signal: /docs/ ai-input=yes\n")
        assert _ai_ok(text, "/docs/intro") is True
        assert _ai_ok(text, "/blog/post") is False


class TestUrlHelpers:
    @pytest.mark.parametrize("url,path", [
        ("https://x.com", "/"),
        ("https://x.com/a/b", "/a/b"),
        ("https://x.com/s?q=1#frag", "/s?q=1"),
    ])
    def test_url_path(self, url, path):
        assert robots.url_path(url) == path

    def test_robots_url(self):
        assert robots.robots_url("https://user@x.com:8443/a?b#c") == "https://user@x.com:8443/robots.txt"


class TestFetch:
    def test_ok_returns_text(self, monkeypatch):
        calls = []
        response = FakeResponse(status_code=200)
        response.content = b"User-agent: *\nDisallow: /\n"

        def fake_get(url, headers=None, timeout=None, allow_redirects=None):
            calls.append((url, headers, timeout))
            return response

        monkeypatch.setattr(robots.requests, "get", fake_get)
        assert robots.fetch("https://x.com/page", UA, timeout=3) == (
            "User-agent: *\nDisallow: /\n", None)
        assert calls == [("https://x.com/robots.txt", {"User-Agent": UA}, 3)]

    def test_body_capped_at_max_bytes(self, monkeypatch):
        response = FakeResponse(status_code=200)
        response.content = b"a" * (robots.MAX_BYTES + 10)
        monkeypatch.setattr(robots.requests, "get", lambda *a, **k: response)
        text, _ = robots.fetch("https://x.com/", UA)
        assert len(text) == robots.MAX_BYTES

    def test_4xx_means_no_restrictions(self, monkeypatch):
        monkeypatch.setattr(robots.requests, "get", lambda *a, **k: FakeResponse(status_code=404))
        assert robots.fetch("https://x.com/", UA) == ("", None)

    def test_5xx_is_a_problem(self, monkeypatch):
        monkeypatch.setattr(robots.requests, "get", lambda *a, **k: FakeResponse(status_code=503))
        text, problem = robots.fetch("https://x.com/", UA)
        assert text is None
        assert "HTTP 503" in problem

    def test_connection_error_is_a_problem(self, monkeypatch):
        def boom(*a, **k):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(robots.requests, "get", boom)
        text, problem = robots.fetch("https://x.com/", UA)
        assert text is None
        assert "ConnectionError" in problem


class TestCheck:
    def _serve(self, monkeypatch, text=None, problem=None):
        monkeypatch.setattr(robots, "fetch", lambda url, ua, timeout=None: (text, problem))

    def test_allowed_is_none(self, monkeypatch):
        self._serve(monkeypatch, "User-agent: *\nAllow: /\n")
        assert robots.check("https://x.com/a", UA, TOKEN) is None

    def test_no_robots_file_allowed(self, monkeypatch):
        self._serve(monkeypatch, "")
        assert robots.check("https://x.com/a", UA, TOKEN) is None

    def test_disallowed_reason(self, monkeypatch):
        self._serve(monkeypatch, "User-agent: *\nDisallow: /\n")
        assert robots.check("https://x.com/a?b=1", UA, TOKEN) == (
            f"x.com's robots.txt disallows /a?b=1 for {TOKEN}")

    def test_ai_opt_out_reason(self, monkeypatch):
        self._serve(monkeypatch, "User-agent: *\nContent-Signal: ai-input=no\n")
        assert robots.check("https://x.com/a", UA, TOKEN) == (
            "x.com's robots.txt opts out of AI input (Content-Signal: ai-input=no)")

    def test_unreadable_counts_as_disallow(self, monkeypatch):
        self._serve(monkeypatch, problem="its robots.txt returned HTTP 503")
        assert robots.check("https://x.com/a", UA, TOKEN) == (
            "x.com: its robots.txt returned HTTP 503, which counts as a full disallow")
