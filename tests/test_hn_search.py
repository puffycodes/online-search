"""Tests for hn_search: query params, Algolia fetch, hit records, text cleanup, and main()."""

import datetime as dt
import json

import pytest
import requests

import hn_search as hs
from helpers import FakeResponse

STORY_HIT = {
    "_tags": ["story", "author_alice", "story_101"],
    "author": "alice",
    "created_at_i": 1704067200,
    "num_comments": 42,
    "objectID": "101",
    "points": 300,
    "title": "Bun 1.0",
    "url": "https://bun.sh/blog/bun-v1.0",
}

ASK_HIT = {
    "_tags": ["story", "author_bob", "story_102", "ask_hn"],
    "author": "bob",
    "created_at_i": 1704067200,
    "num_comments": 7,
    "objectID": "102",
    "points": 12,
    "title": "Ask HN: Bun or Node?",
    "story_text": "Which one?<p>Asking for a friend &amp; colleague.",
}

COMMENT_HIT = {
    "_tags": ["comment", "author_carol", "story_101"],
    "author": "carol",
    "comment_text": "Bun&#x27;s fast.<p>See <a href=\"https://bun.sh\">https://bun.sh</a>",
    "created_at_i": 1704070800,
    "objectID": "201",
    "story_id": 101,
    "story_title": "Bun 1.0",
}


class TestBuildParams:
    def test_defaults(self):
        assert hs.build_params("bun") == {
            "query": "bun",
            "tags": "story",
            "hitsPerPage": hs.RESULTS_TO_SHOW,
            "typoTolerance": "false",
            "queryType": "prefixNone",
        }

    @pytest.mark.parametrize("kind, tag", [
        ("story", "story"), ("comment", "comment"), ("ask", "ask_hn"), ("show", "show_hn"),
    ])
    def test_type_tags(self, kind, tag):
        assert hs.build_params("x", kind=kind)["tags"] == tag

    def test_author_added_to_tags(self):
        assert hs.build_params("x", kind="comment", author="pg")["tags"] == "comment,author_pg"

    def test_date_window_is_inclusive_utc_days(self):
        params = hs.build_params(
            "x", since=dt.date(2024, 1, 1), until=dt.date(2024, 1, 31)
        )
        # 2024-01-01 00:00 UTC up to (not including) 2024-02-01 00:00 UTC
        assert params["numericFilters"] == "created_at_i>=1704067200,created_at_i<1706745600"

    def test_min_points(self):
        assert hs.build_params("x", min_points=0)["numericFilters"] == "points>=0"

    def test_limit(self):
        assert hs.build_params("x", limit=25)["hitsPerPage"] == 25


class TestFetchJson:
    def test_success(self, monkeypatch):
        captured = {}

        def fake_get(url, params, timeout):
            captured.update(url=url, params=params, timeout=timeout)
            return FakeResponse(json_data={"hits": []})

        monkeypatch.setattr(hs.requests, "get", fake_get)
        assert hs.fetch_json("https://u", {"a": 1}) == {"hits": []}
        assert captured == {"url": "https://u", "params": {"a": 1}, "timeout": hs.REQUEST_TIMEOUT}

    def test_algolia_message_surfaced(self, monkeypatch):
        response = FakeResponse(
            status_code=400,
            json_data={"message": "Invalid syntax for numeric condition:x", "status": 400},
        )
        monkeypatch.setattr(hs.requests, "get", lambda url, params, timeout: response)
        with pytest.raises(requests.HTTPError, match="400: Invalid syntax"):
            hs.fetch_json("https://u", {})

    def test_error_without_message_uses_raise_for_status(self, monkeypatch):
        response = FakeResponse(
            status_code=503, raise_for_status=requests.HTTPError("503 Server Error")
        )
        monkeypatch.setattr(hs.requests, "get", lambda url, params, timeout: response)
        with pytest.raises(requests.HTTPError, match="503 Server Error"):
            hs.fetch_json("https://u", {})


class TestSearch:
    def test_relevance_endpoint(self, monkeypatch):
        captured = {}

        def fake_fetch(url, params):
            captured.update(url=url, params=params)
            return {"hits": [STORY_HIT], "nbHits": 777}

        monkeypatch.setattr(hs, "fetch_json", fake_fetch)
        hits, total = hs.search("bun", limit=3)
        assert hits == [STORY_HIT]
        assert total == 777
        assert captured["url"] == hs.SEARCH_URL
        assert captured["params"]["hitsPerPage"] == 3

    def test_date_endpoint(self, monkeypatch):
        captured = {}

        def fake_fetch(url, params):
            captured["url"] = url
            return {"hits": [], "nbHits": 0}

        monkeypatch.setattr(hs, "fetch_json", fake_fetch)
        assert hs.search("bun", sort="date") == ([], 0)
        assert captured["url"] == hs.SEARCH_BY_DATE_URL

    def test_missing_fields(self, monkeypatch):
        monkeypatch.setattr(hs, "fetch_json", lambda url, params: {})
        assert hs.search("bun") == ([], 0)


class TestCleanText:
    def test_empty(self):
        assert hs.clean_text(None) is None
        assert hs.clean_text("") is None
        assert hs.clean_text("<p>") is None

    def test_paragraphs_tags_and_entities(self):
        text = hs.clean_text("It&#x27;s <i>fast</i>.<p>See <a href=\"u\">link</a> &amp; more")
        assert text == "It's fast.\n\nSee link & more"

    def test_truncated(self):
        assert hs.clean_text("abcdefghij", max_chars=4) == "abcd..."

    def test_no_limit(self):
        assert hs.clean_text("a" * 1000, max_chars=0) == "a" * 1000


class TestHitToDict:
    def test_story(self):
        assert hs.hit_to_dict(1, STORY_HIT) == {
            "rank": 1,
            "type": "story",
            "title": "Bun 1.0",
            "author": "alice",
            "posted": "2024-01-01 00:00 UTC",
            "score": 300,
            "comments": 42,
            "url": "https://bun.sh/blog/bun-v1.0",
            "discussion_url": "https://news.ycombinator.com/item?id=101",
            "text": None,
        }

    def test_self_post_links_to_thread_and_has_text(self):
        row = hs.hit_to_dict(2, ASK_HIT)
        assert row["url"] == "https://news.ycombinator.com/item?id=102"
        assert row["text"] == "Which one?\n\nAsking for a friend & colleague."

    def test_comment(self):
        assert hs.hit_to_dict(3, COMMENT_HIT) == {
            "rank": 3,
            "type": "comment",
            "title": "Bun 1.0",
            "author": "carol",
            "posted": "2024-01-01 01:00 UTC",
            "score": None,
            "comments": None,
            "url": "https://news.ycombinator.com/item?id=201",
            "discussion_url": "https://news.ycombinator.com/item?id=101",
            "text": "Bun's fast.\n\nSee https://bun.sh",
        }

    def test_text_cut_to_max_chars(self):
        assert hs.hit_to_dict(1, COMMENT_HIT, max_chars=5)["text"] == "Bun's..."

    def test_story_defaults(self):
        row = hs.hit_to_dict(1, {"objectID": "9", "_tags": ["story"]})
        assert row["title"] == "(no title)"
        assert row["score"] == 0
        assert row["comments"] == 0
        assert row["url"] == row["discussion_url"] == "https://news.ycombinator.com/item?id=9"

    def test_comment_without_story(self):
        row = hs.hit_to_dict(1, {"objectID": "9", "_tags": ["comment"]})
        assert row["title"] == "(no title)"
        assert row["discussion_url"] is None


class TestFormatHit:
    def test_story(self):
        out = hs.format_hit(hs.hit_to_dict(1, STORY_HIT))
        assert out.splitlines()[0] == "1. Bun 1.0"
        assert "Score: 300  |  Comments: 42  |  Posted: 2024-01-01 00:00 UTC  |  By: alice" in out
        assert "Link: https://bun.sh/blog/bun-v1.0" in out
        assert "Discussion: https://news.ycombinator.com/item?id=101" in out

    def test_story_text_indented(self):
        out = hs.format_hit(hs.hit_to_dict(2, ASK_HIT))
        assert "\n   Which one?\n\n   Asking for a friend & colleague." in out

    def test_comment(self):
        out = hs.format_hit(hs.hit_to_dict(3, COMMENT_HIT))
        assert out.splitlines()[0] == '3. Comment by carol on "Bun 1.0"'
        assert "Comment: https://news.ycombinator.com/item?id=201" in out
        assert "Discussion: https://news.ycombinator.com/item?id=101" in out
        assert "Score" not in out

    def test_comment_without_story_has_no_discussion_line(self):
        out = hs.format_hit(hs.hit_to_dict(1, {"objectID": "9", "_tags": ["comment"]}))
        assert "Discussion:" not in out


class TestParseArgs:
    def test_defaults(self):
        args = hs.parse_args(["bun"])
        assert args.query == "bun"
        assert args.type == "story"
        assert args.sort == "relevance"
        assert args.since is None and args.until is None
        assert args.min_points is None and args.author is None
        assert args.limit == hs.RESULTS_TO_SHOW
        assert args.max_chars == hs.TEXT_CHARS
        assert args.json is False

    def test_flags(self):
        args = hs.parse_args([
            "bun", "--type", "ask", "--sort", "date", "--since", "2024-01-01",
            "--until", "2024-01-31", "--min-points", "10", "--author", "pg",
            "--limit", "100", "--max-chars", "0", "--json",
        ])
        assert args.type == "ask"
        assert args.sort == "date"
        assert args.since == dt.date(2024, 1, 1)
        assert args.until == dt.date(2024, 1, 31)
        assert args.min_points == 10
        assert args.author == "pg"
        assert args.limit == 100
        assert args.max_chars == 0
        assert args.json is True

    @pytest.mark.parametrize("argv", [
        ["   "],
        ["bun", "--type", "job"],
        ["bun", "--sort", "points"],
        ["bun", "--since", "2024-13-01"],
        ["bun", "--since", "2024-02-01", "--until", "2024-01-31"],
        ["bun", "--type", "comment", "--min-points", "5"],
        ["bun", "--min-points", "-1"],
        ["bun", "--limit", "0"],
        ["bun", "--limit", str(hs.MAX_RESULTS + 1)],
        ["bun", "--max-chars", "-5"],
        ["bun", "--author", "bad name"],
    ])
    def test_invalid_rejected(self, argv):
        with pytest.raises(SystemExit) as exc:
            hs.parse_args(argv)
        assert exc.value.code == 2


class TestMain:
    def _fake_search(self, captured, hits=(STORY_HIT,), total=777):
        def fake(query, **kwargs):
            captured.update(kwargs, query=query)
            return list(hits), total
        return fake

    def test_json_output(self, monkeypatch, capsys):
        captured = {}
        monkeypatch.setattr(hs, "search", self._fake_search(captured))
        hs.main(["bun", "--since", "2024-01-01", "--limit", "3", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["query"] == "bun"
        assert payload["type"] == "story"
        assert payload["sort"] == "relevance"
        assert payload["since"] == "2024-01-01"
        assert payload["until"] is None
        assert payload["total_matches"] == 777
        assert payload["results"][0]["title"] == "Bun 1.0"
        assert captured["limit"] == 3
        assert captured["since"] == dt.date(2024, 1, 1)

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(hs, "search", self._fake_search({}, hits=[COMMENT_HIT], total=53))
        hs.main(["bun", "--type", "comment", "--sort", "date"])
        out = capsys.readouterr().out
        assert "Searching Hacker News for 'bun'..." in out
        assert "53 matching comments; showing 1, by date." in out
        assert 'Comment by carol on "Bun 1.0"' in out

    def test_max_chars_applied(self, monkeypatch, capsys):
        monkeypatch.setattr(hs, "search", self._fake_search({}, hits=[COMMENT_HIT]))
        hs.main(["bun", "--type", "comment", "--max-chars", "5", "--json"])
        assert json.loads(capsys.readouterr().out)["results"][0]["text"] == "Bun's..."

    def test_no_results_text(self, monkeypatch, capsys):
        monkeypatch.setattr(hs, "search", self._fake_search({}, hits=[], total=0))
        hs.main(["zzqq"])
        assert "No results found." in capsys.readouterr().out

    def test_no_results_json(self, monkeypatch, capsys):
        monkeypatch.setattr(hs, "search", self._fake_search({}, hits=[], total=0))
        hs.main(["zzqq", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["results"] == []
        assert payload["total_matches"] == 0

    def test_request_error_exits_json(self, monkeypatch, capsys):
        def boom(query, **kwargs):
            raise requests.ConnectionError("network down")

        monkeypatch.setattr(hs, "search", boom)
        with pytest.raises(SystemExit) as exc:
            hs.main(["bun", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "network down"}

    def test_non_json_body_exits_text(self, monkeypatch, capsys):
        def boom(query, **kwargs):
            raise ValueError("Expecting value")

        monkeypatch.setattr(hs, "search", boom)
        with pytest.raises(SystemExit) as exc:
            hs.main(["bun"])
        assert exc.value.code == 1
        assert "Error: Expecting value" in capsys.readouterr().err
