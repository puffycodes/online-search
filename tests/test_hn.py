"""Tests for hn: JSON fetching, HN item fetch, hottest stories, item ids, link/time helpers, and HTML text cleanup."""

import pytest
import requests

import hn
from helpers import FakeResponse


class TestFetchJson:
    def test_success(self, monkeypatch):
        captured = {}

        def fake_get(url, params, timeout):
            captured.update(url=url, params=params, timeout=timeout)
            return FakeResponse(json_data={"hits": []})

        monkeypatch.setattr(hn.requests, "get", fake_get)
        assert hn.fetch_json("https://u", {"a": 1}) == {"hits": []}
        assert captured == {"url": "https://u", "params": {"a": 1}, "timeout": hn.REQUEST_TIMEOUT}

    def test_defaults_and_custom_timeout(self, monkeypatch):
        captured = {}

        def fake_get(url, params, timeout):
            captured.update(params=params, timeout=timeout)
            return FakeResponse(json_data=[1, 2])

        monkeypatch.setattr(hn.requests, "get", fake_get)
        assert hn.fetch_json("https://u", timeout=30) == [1, 2]
        assert captured == {"params": None, "timeout": 30}

    def test_algolia_message_surfaced(self, monkeypatch):
        response = FakeResponse(
            status_code=400,
            json_data={"message": "Invalid syntax for numeric condition:x", "status": 400},
        )
        monkeypatch.setattr(hn.requests, "get", lambda url, params, timeout: response)
        with pytest.raises(requests.HTTPError, match="400: Invalid syntax"):
            hn.fetch_json("https://u", {})

    def test_error_without_message_uses_raise_for_status(self, monkeypatch):
        response = FakeResponse(
            status_code=503, raise_for_status=requests.HTTPError("503 Server Error")
        )
        monkeypatch.setattr(hn.requests, "get", lambda url, params, timeout: response)
        with pytest.raises(requests.HTTPError, match="503 Server Error"):
            hn.fetch_json("https://u", {})


class TestFetchStory:
    def test_returns_payload_from_item_url(self, monkeypatch):
        captured = {}

        def fake_fetch(url):
            captured["url"] = url
            return {"id": 1, "type": "story"}

        monkeypatch.setattr(hn, "fetch_json", fake_fetch)
        assert hn.fetch_story(1) == {"id": 1, "type": "story"}
        assert captured["url"] == "https://hacker-news.firebaseio.com/v0/item/1.json"

    def test_missing_item_is_none(self, monkeypatch):
        monkeypatch.setattr(hn, "fetch_json", lambda url: None)
        assert hn.fetch_story(1) is None

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


class TestFetchHottest:
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
        out = hn.fetch_hottest(limit=10)
        assert [s["id"] for s in out] == [1, 3]

    def test_skips_items_that_failed_to_fetch(self, monkeypatch):
        self._wire(monkeypatch, {1: {"id": 1, "type": "story", "score": 10}}, ids=[1, 2])
        assert [s["id"] for s in hn.fetch_hottest(limit=10)] == [1]

    def test_sorts_by_score_desc_and_limits(self, monkeypatch):
        self._wire(monkeypatch, {
            1: {"id": 1, "type": "story", "score": 10},
            2: {"id": 2, "type": "story", "score": 50},
            3: {"id": 3, "type": "story", "score": 30},
        })
        out = hn.fetch_hottest(limit=2)
        assert [s["id"] for s in out] == [2, 3]

    def test_only_inspects_candidate_pool(self, monkeypatch):
        stories = {i: {"id": i, "type": "story", "score": i} for i in range(1, 60)}
        # id 99 has the top score but sits past the candidate pool slice
        stories[99] = {"id": 99, "type": "story", "score": 9999}
        ids = list(range(1, 60)) + [99]
        self._wire(monkeypatch, stories, ids=ids)
        out = hn.fetch_hottest(limit=5)
        assert 99 not in [s["id"] for s in out]

    def test_candidate_pool_scales_with_limit(self, monkeypatch):
        fetched = []
        stories = {i: {"id": i, "type": "story", "score": i} for i in range(1, 301)}
        monkeypatch.setattr(hn, "fetch_json", lambda url: list(range(1, 301)))
        monkeypatch.setattr(hn, "fetch_story", lambda i: fetched.append(i) or stories[i])
        out = hn.fetch_hottest(limit=50)
        assert len(fetched) == 50 * hn.CANDIDATE_POOL_FACTOR
        # 50 results, not capped at a fixed pool: the top scores in the first 200.
        assert [s["id"] for s in out] == list(range(200, 150, -1))


class TestParseItemId:
    @pytest.mark.parametrize("value, expected", [
        ("48843352", 48843352),
        (" 42 ", 42),
        ("https://news.ycombinator.com/item?id=48843352", 48843352),
        ("news.ycombinator.com/item?id=7", 7),
        ("https://news.ycombinator.com/item?p=2&id=99", 99),
    ])
    def test_valid(self, value, expected):
        assert hn.parse_item_id(value) == expected

    @pytest.mark.parametrize("value", ["", "abc", "https://example.com/?id=5", "-3"])
    def test_invalid(self, value):
        with pytest.raises(ValueError):
            hn.parse_item_id(value)


class TestLinkAndTime:
    def test_discussion_url(self):
        assert hn.discussion_url({"id": 42}) == "https://news.ycombinator.com/item?id=42"

    def test_posted_at_fixed_timestamp(self):
        assert hn.posted_at({"time": 1704067200}) == "2024-01-01 00:00 UTC"

    def test_posted_at_missing_time(self):
        assert hn.posted_at({}) == "1970-01-01 00:00 UTC"


class TestCleanText:
    def test_empty(self):
        assert hn.clean_text(None) is None
        assert hn.clean_text("") is None
        assert hn.clean_text("<p>") is None

    def test_paragraphs_tags_and_entities(self):
        text = hn.clean_text("It&#x27;s <i>fast</i>.<p>See <a href=\"u\">link</a> &amp; more")
        assert text == "It's fast.\n\nSee link & more"

    def test_extra_blank_lines_collapsed(self):
        assert hn.clean_text("a<p><p><p>b") == "a\n\nb"

    def test_truncated(self):
        assert hn.clean_text("abcdefghij", max_chars=4) == "abcd..."

    def test_default_limit(self):
        assert hn.clean_text("a" * (hn.TEXT_CHARS + 1)) == "a" * hn.TEXT_CHARS + "..."

    def test_no_limit(self):
        assert hn.clean_text("a" * 1000, max_chars=0) == "a" * 1000
