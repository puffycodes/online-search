"""Tests for hn_search: query params, search endpoints, hit records, and main()."""

import datetime as dt
import json

import pytest
import requests

import hn_search as hs

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


def _job_comment(object_id, story_id, month="October 2026", kind="Who is hiring?"):
    return {
        "_tags": ["comment", f"story_{story_id}"],
        "author": "recruiter",
        "comment_text": "Acme | Swift engineer | REMOTE",
        "created_at_i": 1704070800,
        "objectID": str(object_id),
        "story_id": story_id,
        "story_title": f"Ask HN: {kind} ({month})",
    }


class TestJobThreads:
    @pytest.mark.parametrize("title", [
        "Ask HN: Who is hiring? (October 2026)",
        "Ask HN: Who Is Hiring? (October 2010 Edition)",
        "Ask HN: Who is Hiring? (July 2011)",
        "Ask HN: Who wants to be hired? (October 2026)",
        "Ask HN: Who wants to be hired?",
        "Ask HN: Freelancer? Seeking freelancer? (August 2026)",
        "Ask HN: Freelancer? Seeking Freelancer? (May 2013)",
        "Ask HN: Freelancer? Seeking freelancers? (May 2011)",
        " Ask HN: Freelancer? Seeking freelancer? (February 2012)",
    ])
    def test_job_thread_titles(self, title):
        assert hs.is_job_thread(title)

    @pytest.mark.parametrize("title", [
        None,
        "",
        "Bun 1.0",
        "Ask HN: Who is hiring right now?",
        "Ask HN: Have the whoishiring posts been useful? Can we do better?",
        "Show HN: Who is hiring refugees?",
        "Tell HN: Ask HN: Who is hiring? is moving",
    ])
    def test_other_titles(self, title):
        assert not hs.is_job_thread(title)

    def test_is_job_hit_for_comments_and_stories(self):
        assert hs.is_job_hit(_job_comment(1, 900))
        assert not hs.is_job_hit(COMMENT_HIT)
        story = {"_tags": ["story"], "objectID": "900",
                 "title": "Ask HN: Who is hiring? (October 2026)"}
        assert hs.is_job_hit(story)
        assert not hs.is_job_hit(STORY_HIT)


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

    def test_story_added_to_tags(self):
        params = hs.build_params("x", kind="comment", author="pg", story=48843352)
        assert params["tags"] == "comment,author_pg,story_48843352"

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

    def test_excluded_stories_are_negative_tags(self):
        params = hs.build_params("x", kind="comment", author="pg", exclude_stories=[5, 6])
        assert params["tags"] == "comment,author_pg,-story_5,-story_6"


def _scripted_fetch(monkeypatch, responses):
    """Make fetch_json return `responses` in turn; returns the params list sent."""
    sent = []
    queue = list(responses)

    def fake_fetch(url, params):
        sent.append(params)
        return queue.pop(0)

    monkeypatch.setattr(hs, "fetch_json", fake_fetch)
    return sent


class TestSearch:
    def test_relevance_endpoint(self, monkeypatch):
        captured = {}

        def fake_fetch(url, params):
            captured.update(url=url, params=params)
            return {"hits": [STORY_HIT], "nbHits": 777}

        monkeypatch.setattr(hs, "fetch_json", fake_fetch)
        hits, total, job_threads = hs.search("bun", limit=3)
        assert hits == [STORY_HIT]
        assert total == 777
        assert job_threads == 0
        assert captured["url"] == hs.SEARCH_URL
        assert captured["params"]["hitsPerPage"] == 3

    def test_date_endpoint(self, monkeypatch):
        captured = {}

        def fake_fetch(url, params):
            captured["url"] = url
            return {"hits": [], "nbHits": 0}

        monkeypatch.setattr(hs, "fetch_json", fake_fetch)
        assert hs.search("bun", sort="date") == ([], 0, 0)
        assert captured["url"] == hs.SEARCH_BY_DATE_URL

    def test_story_passed_through(self, monkeypatch):
        captured = {}

        def fake_fetch(url, params):
            captured.update(params)
            return {"hits": [], "nbHits": 0}

        monkeypatch.setattr(hs, "fetch_json", fake_fetch)
        hs.search("fuzzing", kind="comment", story=7)
        assert captured["tags"] == "comment,story_7"

    def test_missing_fields(self, monkeypatch):
        monkeypatch.setattr(hs, "fetch_json", lambda url, params: {})
        assert hs.search("bun") == ([], 0, 0)


class TestSearchJobThreads:
    def test_found_threads_excluded_and_search_rerun(self, monkeypatch):
        sent = _scripted_fetch(monkeypatch, [
            {"hits": [_job_comment(1, 900), COMMENT_HIT, _job_comment(2, 800)], "nbHits": 50},
            {"hits": [COMMENT_HIT], "nbHits": 40},
        ])
        hits, total, job_threads = hs.search("swift", kind="comment")
        assert hits == [COMMENT_HIT]
        assert (total, job_threads) == (40, 2)
        assert [p["tags"] for p in sent] == ["comment", "comment,-story_800,-story_900"]

    def test_exclusions_accumulate_over_rounds(self, monkeypatch):
        sent = _scripted_fetch(monkeypatch, [
            {"hits": [_job_comment(1, 900)], "nbHits": 9},
            {"hits": [_job_comment(2, 800), COMMENT_HIT], "nbHits": 8},
            {"hits": [COMMENT_HIT], "nbHits": 7},
        ])
        hits, total, job_threads = hs.search("swift", kind="comment")
        assert (hits, total, job_threads) == ([COMMENT_HIT], 7, 2)
        assert sent[-1]["tags"] == "comment,-story_900,-story_800"

    def test_clean_first_page_takes_one_request(self, monkeypatch):
        sent = _scripted_fetch(monkeypatch, [{"hits": [COMMENT_HIT], "nbHits": 1}])
        assert hs.search("bun", kind="comment") == ([COMMENT_HIT], 1, 0)
        assert len(sent) == 1

    def test_stops_at_max_rounds_and_drops_leftovers(self, monkeypatch):
        responses = [{"hits": [_job_comment(i, 900 + i), COMMENT_HIT], "nbHits": 100 - i}
                     for i in range(hs.MAX_JOB_ROUNDS)]
        sent = _scripted_fetch(monkeypatch, responses)
        hits, total, job_threads = hs.search("swift", kind="comment")
        assert len(sent) == hs.MAX_JOB_ROUNDS
        assert hits == [COMMENT_HIT]
        assert job_threads == hs.MAX_JOB_ROUNDS
        assert total == 100 - (hs.MAX_JOB_ROUNDS - 1)

    def test_job_hit_without_id_dropped_and_counted(self, monkeypatch):
        no_id = {**_job_comment(1, 900), "story_id": None}
        sent = _scripted_fetch(monkeypatch, [{"hits": [no_id, COMMENT_HIT], "nbHits": 2}])
        assert hs.search("swift", kind="comment") == ([COMMENT_HIT], 2, 1)
        assert len(sent) == 1

    def test_job_thread_stories_excluded(self, monkeypatch):
        job_story = {"_tags": ["story", "story_900"], "objectID": "900",
                     "title": "Ask HN: Who is hiring? (October 2026)"}
        sent = _scripted_fetch(monkeypatch, [
            {"hits": [job_story, STORY_HIT], "nbHits": 2},
            {"hits": [STORY_HIT], "nbHits": 1},
        ])
        assert hs.search("hiring") == ([STORY_HIT], 1, 1)
        assert sent[1]["tags"] == "story,-story_900"

    def test_include_job_threads_keeps_them(self, monkeypatch):
        job = _job_comment(1, 900)
        sent = _scripted_fetch(monkeypatch, [{"hits": [job], "nbHits": 1}])
        assert hs.search("swift", kind="comment", include_job_threads=True) == ([job], 1, 0)
        assert len(sent) == 1

    def test_story_search_is_not_filtered(self, monkeypatch):
        job = _job_comment(1, 900)
        sent = _scripted_fetch(monkeypatch, [{"hits": [job], "nbHits": 1}])
        assert hs.search("swift", kind="comment", story=900) == ([job], 1, 0)
        assert sent[0]["tags"] == "comment,story_900"


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
        assert args.include_job_threads is False
        assert args.json is False

    def test_include_job_threads_flag(self):
        assert hs.parse_args(["bun", "--include-job-threads"]).include_job_threads is True

    @pytest.mark.parametrize("argv", [
        ["fuzzing", "--story", "48843352"],
        ["fuzzing", "--story", "https://news.ycombinator.com/item?id=48843352"],
        ["fuzzing", "--story", "48843352", "--type", "comment"],
    ])
    def test_story_implies_comments(self, argv):
        args = hs.parse_args(argv)
        assert args.story == 48843352
        assert args.type == "comment"

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
        ["bun", "--story", "abc"],
        ["bun", "--story", "https://example.com/?id=5"],
        ["bun", "--story", "5", "--type", "story"],
        ["bun", "--story", "5", "--type", "ask"],
        ["bun", "--story", "5", "--min-points", "1"],
    ])
    def test_invalid_rejected(self, argv):
        with pytest.raises(SystemExit) as exc:
            hs.parse_args(argv)
        assert exc.value.code == 2


class TestMain:
    def _fake_search(self, captured, hits=(STORY_HIT,), total=777, job_threads=0):
        def fake(query, **kwargs):
            captured.update(kwargs, query=query)
            return list(hits), total, job_threads
        return fake

    def test_job_threads_reported_json(self, monkeypatch, capsys):
        captured = {}
        monkeypatch.setattr(hs, "search", self._fake_search(captured, job_threads=3))
        hs.main(["swift", "--json"])
        assert json.loads(capsys.readouterr().out)["job_threads_skipped"] == 3
        assert captured["include_job_threads"] is False

    def test_job_threads_reported_text(self, monkeypatch, capsys):
        monkeypatch.setattr(hs, "search", self._fake_search({}, job_threads=1))
        hs.main(["swift"])
        assert "(Left out 1 job thread; --include-job-threads keeps them.)" in capsys.readouterr().out

    def test_job_threads_reported_with_no_results(self, monkeypatch, capsys):
        monkeypatch.setattr(hs, "search", self._fake_search({}, hits=[], total=0, job_threads=2))
        hs.main(["hiring"])
        out = capsys.readouterr().out
        assert "No results found." in out
        assert "Left out 2 job threads" in out

    def test_no_job_threads_no_note(self, monkeypatch, capsys):
        monkeypatch.setattr(hs, "search", self._fake_search({}))
        hs.main(["bun"])
        assert "Left out" not in capsys.readouterr().out

    def test_include_job_threads_passed_through(self, monkeypatch, capsys):
        captured = {}
        monkeypatch.setattr(hs, "search", self._fake_search(captured))
        hs.main(["swift", "--include-job-threads", "--json"])
        assert captured["include_job_threads"] is True

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
        assert payload["story"] is None
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
        out = capsys.readouterr().out
        assert "No results found." in out
        assert "--story" not in out

    def test_story_search(self, monkeypatch, capsys):
        captured = {}
        monkeypatch.setattr(
            hs, "search", self._fake_search(captured, hits=[COMMENT_HIT], total=23)
        )
        hs.main(["fuzzing", "--story", "https://news.ycombinator.com/item?id=101"])
        out = capsys.readouterr().out
        assert "23 matching comments in thread 101; showing 1, by relevance." in out
        assert captured["story"] == 101
        assert captured["kind"] == "comment"

    def test_story_search_json(self, monkeypatch, capsys):
        monkeypatch.setattr(hs, "search", self._fake_search({}, hits=[COMMENT_HIT], total=1))
        hs.main(["fuzzing", "--story", "101", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["story"] == 101
        assert payload["type"] == "comment"

    def test_story_no_results_hint(self, monkeypatch, capsys):
        monkeypatch.setattr(hs, "search", self._fake_search({}, hits=[], total=0))
        hs.main(["fuzzing", "--story", "102"])
        assert "--story needs the story's id" in capsys.readouterr().out

    def test_singular_counts(self, monkeypatch, capsys):
        monkeypatch.setattr(hs, "search", self._fake_search({}, total=1))
        hs.main(["bun"])
        assert "1 matching story; showing 1" in capsys.readouterr().out

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
