"""Tests for hottest_tech_discussions: story helpers, fetch_story, ranking, and main()."""

import json

import pytest
import requests

import hottest_tech_discussions as hn


class TestSmallHelpers:
    def test_discussion_url(self):
        assert hn.discussion_url({"id": 42}) == "https://news.ycombinator.com/item?id=42"

    def test_posted_at_fixed_timestamp(self):
        assert hn.posted_at({"time": 1704067200}) == "2024-01-01 00:00 UTC"

    def test_posted_at_missing_time(self):
        assert hn.posted_at({}) == "1970-01-01 00:00 UTC"

    def test_story_to_dict_full(self):
        story = {"title": "T", "score": 5, "descendants": 3, "time": 1704067200,
                 "url": "http://x", "id": 9}
        row = hn.story_to_dict(1, story)
        assert row["rank"] == 1
        assert row["comments"] == 3
        assert row["url"] == "http://x"
        assert row["discussion_url"] == "https://news.ycombinator.com/item?id=9"

    def test_story_to_dict_defaults(self):
        row = hn.story_to_dict(2, {"id": 7})
        assert row["title"] == "(no title)"
        assert row["score"] == 0
        assert row["comments"] == 0
        assert row["url"] == row["discussion_url"] == "https://news.ycombinator.com/item?id=7"


class TestFetchStory:
    def test_swallows_request_error(self, monkeypatch):
        def boom(url):
            raise requests.RequestException("x")

        monkeypatch.setattr(hn, "fetch_json", boom)
        assert hn.fetch_story(1) is None

    def test_swallows_value_error(self, monkeypatch):
        def boom(url):
            raise ValueError("bad json")

        monkeypatch.setattr(hn, "fetch_json", boom)
        assert hn.fetch_story(1) is None

    def test_returns_payload(self, monkeypatch):
        monkeypatch.setattr(hn, "fetch_json", lambda url: {"id": 1, "type": "story"})
        assert hn.fetch_story(1) == {"id": 1, "type": "story"}


class TestGetHottest:
    def _wire(self, monkeypatch, stories_by_id, ids=None):
        ids = ids if ids is not None else sorted(stories_by_id)
        monkeypatch.setattr(hn, "fetch_json", lambda url: list(ids))
        monkeypatch.setattr(hn, "fetch_story", lambda i: stories_by_id.get(i))

    def test_filters_non_story_types(self, monkeypatch):
        self._wire(monkeypatch, {
            1: {"id": 1, "type": "story", "score": 10},
            2: {"id": 2, "type": "job", "score": 99},
            3: {"id": 3, "type": "story", "score": 5},
        })
        out = hn.get_hottest_tech_discussions(limit=10)
        assert [s["id"] for s in out] == [1, 3]

    def test_sorts_by_score_desc_and_limits(self, monkeypatch):
        self._wire(monkeypatch, {
            1: {"id": 1, "type": "story", "score": 10},
            2: {"id": 2, "type": "story", "score": 50},
            3: {"id": 3, "type": "story", "score": 30},
        })
        out = hn.get_hottest_tech_discussions(limit=2)
        assert [s["id"] for s in out] == [2, 3]

    def test_only_inspects_candidate_pool(self, monkeypatch):
        stories = {i: {"id": i, "type": "story", "score": i} for i in range(1, 60)}
        # id 99 has the top score but sits past the candidate pool slice
        stories[99] = {"id": 99, "type": "story", "score": 9999}
        ids = list(range(1, 60)) + [99]
        self._wire(monkeypatch, stories, ids=ids)
        out = hn.get_hottest_tech_discussions(limit=5)
        assert 99 not in [s["id"] for s in out]

    def test_candidate_pool_scales_with_limit(self, monkeypatch):
        fetched = []
        stories = {i: {"id": i, "type": "story", "score": i} for i in range(1, 301)}
        monkeypatch.setattr(hn, "fetch_json", lambda url: list(range(1, 301)))
        monkeypatch.setattr(hn, "fetch_story", lambda i: fetched.append(i) or stories[i])
        out = hn.get_hottest_tech_discussions(limit=50)
        assert len(fetched) == 50 * hn.CANDIDATE_POOL_FACTOR
        # 50 results, not capped at a fixed pool: the top scores in the first 200.
        assert [s["id"] for s in out] == list(range(200, 150, -1))


class TestMain:
    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            hn, "get_hottest_tech_discussions",
            lambda limit: [{"id": 1, "title": "T", "score": 5, "descendants": 2,
                            "time": 1704067200, "url": "http://x"}],
        )
        hn.main(["--json"])
        rows = json.loads(capsys.readouterr().out)
        assert rows[0]["rank"] == 1 and rows[0]["title"] == "T"

    def test_error_exits(self, monkeypatch, capsys):
        def boom(limit):
            raise requests.RequestException("down")

        monkeypatch.setattr(hn, "get_hottest_tech_discussions", boom)
        with pytest.raises(SystemExit):
            hn.main(["--json"])
        assert json.loads(capsys.readouterr().err) == {"error": "down"}

    def test_empty_text(self, monkeypatch, capsys):
        monkeypatch.setattr(hn, "get_hottest_tech_discussions", lambda limit: [])
        hn.main([])
        assert "No stories found." in capsys.readouterr().out

    @pytest.mark.parametrize("bad", ["0", "-1", "abc"])
    def test_invalid_limit_exits_2_before_fetch(self, monkeypatch, bad):
        def fail(limit):
            raise AssertionError("should not fetch")

        monkeypatch.setattr(hn, "get_hottest_tech_discussions", fail)
        with pytest.raises(SystemExit) as exc:
            hn.main(["--limit", bad])
        assert exc.value.code == 2
