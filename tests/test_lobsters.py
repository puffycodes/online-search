"""Tests for lobsters: page fetching, ranking, tag filtering, and posting times."""

import pytest
import requests

import lobsters as lob
from helpers import FakeResponse


def story(short_id, score=1, tags=None, **extra):
    return {"short_id": short_id, "score": score, "tags": tags or [], **extra}


class TestFetchPage:
    def test_first_page_is_hottest(self, monkeypatch):
        calls = []

        def fake_get(url, headers=None, timeout=None):
            calls.append((url, headers, timeout))
            return FakeResponse(json_data=[story("a")])

        monkeypatch.setattr(lob.requests, "get", fake_get)
        assert lob.fetch_page(1) == [story("a")]
        assert calls == [(lob.HOTTEST_URL, lob.HEADERS, lob.REQUEST_TIMEOUT)]

    def test_later_pages(self, monkeypatch):
        urls = []
        monkeypatch.setattr(
            lob.requests, "get",
            lambda url, **k: urls.append(url) or FakeResponse(json_data=[]),
        )
        lob.fetch_page(3)
        assert urls == ["https://lobste.rs/page/3.json"]

    def test_error_status_raises(self, monkeypatch):
        error = requests.HTTPError("404 Client Error")
        monkeypatch.setattr(
            lob.requests, "get",
            lambda url, **k: FakeResponse(status_code=404, raise_for_status=error),
        )
        with pytest.raises(requests.HTTPError):
            lob.fetch_page(2)

    def test_non_list_raises(self, monkeypatch):
        monkeypatch.setattr(
            lob.requests, "get", lambda url, **k: FakeResponse(json_data={"error": "x"})
        )
        with pytest.raises(ValueError, match="expected a list"):
            lob.fetch_page(1)


class TestFetchHottest:
    def _wire(self, monkeypatch, pages):
        fetched = []

        def fake_fetch(page):
            fetched.append(page)
            return pages.get(page, [])

        monkeypatch.setattr(lob, "fetch_page", fake_fetch)
        return fetched

    def test_sorts_by_score_desc_and_limits(self, monkeypatch):
        self._wire(monkeypatch, {1: [story("a", 10), story("b", 50), story("c", 30)]})
        out = lob.fetch_hottest(limit=2)
        assert [s["short_id"] for s in out] == ["b", "c"]

    def test_default_pool_fetches_two_pages(self, monkeypatch):
        # 10 x 4 = 40 candidates, at 25 a page.
        fetched = self._wire(monkeypatch, {p: [story(f"{p}-{i}") for i in range(25)] for p in (1, 2, 3)})
        lob.fetch_hottest(limit=10)
        assert fetched == [1, 2]

    def test_empty_page_stops_early(self, monkeypatch):
        fetched = self._wire(monkeypatch, {})
        assert lob.fetch_hottest(limit=10) == []
        assert fetched == [1]

    def test_pages_capped(self, monkeypatch):
        pages = {p: [story(f"{p}-{i}") for i in range(25)] for p in range(1, 50)}
        fetched = self._wire(monkeypatch, pages)
        lob.fetch_hottest(limit=500)
        assert fetched == list(range(1, lob.MAX_PAGES + 1))

    def test_only_ranks_candidate_pool(self, monkeypatch):
        # limit 1 -> pool of 4: the high score in 5th place is out of reach.
        self._wire(monkeypatch, {1: [story(str(i), i) for i in range(1, 5)] + [story("x", 999)]})
        out = lob.fetch_hottest(limit=1)
        assert out[0]["short_id"] == "4"

    def test_drops_repeats_across_pages(self, monkeypatch):
        self._wire(monkeypatch, {
            1: [story(str(i)) for i in range(24)] + [story("dup", 5)],
            2: [story("dup", 5), story("z", 3)],
        })
        out = lob.fetch_hottest(limit=10)
        assert [s["short_id"] for s in out].count("dup") == 1

    def test_excludes_tags_case_insensitively(self, monkeypatch):
        self._wire(monkeypatch, {1: [
            story("meta", 99, ["announce", "meta"]),
            story("rust", 10, ["rust"]),
            story("plain", 5),
        ]})
        out = lob.fetch_hottest(limit=10, exclude_tags=["META"])
        assert [s["short_id"] for s in out] == ["rust", "plain"]


class TestPostedAt:
    def test_converts_offset_to_utc(self):
        assert lob.posted_at({"created_at": "2026-10-18T20:28:53.196-05:00"}) == "2026-10-19 01:28 UTC"

    @pytest.mark.parametrize("value", [None, "", "yesterday"])
    def test_unreadable_is_none(self, value):
        assert lob.posted_at({"created_at": value}) is None

    def test_missing_is_none(self):
        assert lob.posted_at({}) is None
