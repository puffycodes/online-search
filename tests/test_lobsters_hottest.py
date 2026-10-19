"""Tests for lobsters_hottest: page fetching, ranking, tag filtering, story records, and main()."""

import json

import pytest
import requests

import lobsters_hottest as lob
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


class TestGetLobstersHottest:
    def _wire(self, monkeypatch, pages):
        fetched = []

        def fake_fetch(page):
            fetched.append(page)
            return pages.get(page, [])

        monkeypatch.setattr(lob, "fetch_page", fake_fetch)
        return fetched

    def test_sorts_by_score_desc_and_limits(self, monkeypatch):
        self._wire(monkeypatch, {1: [story("a", 10), story("b", 50), story("c", 30)]})
        out = lob.get_lobsters_hottest(limit=2)
        assert [s["short_id"] for s in out] == ["b", "c"]

    def test_default_fetches_two_pages(self, monkeypatch):
        # 10 x 4 = 40 candidates, at 25 a page.
        fetched = self._wire(monkeypatch, {p: [story(f"{p}-{i}") for i in range(25)] for p in (1, 2, 3)})
        lob.get_lobsters_hottest(limit=10)
        assert fetched == [1, 2]

    def test_empty_page_stops_early(self, monkeypatch):
        fetched = self._wire(monkeypatch, {})
        assert lob.get_lobsters_hottest(limit=10) == []
        assert fetched == [1]

    def test_pages_capped(self, monkeypatch):
        pages = {p: [story(f"{p}-{i}") for i in range(25)] for p in range(1, 50)}
        fetched = self._wire(monkeypatch, pages)
        lob.get_lobsters_hottest(limit=500)
        assert fetched == list(range(1, lob.MAX_PAGES + 1))

    def test_only_ranks_candidate_pool(self, monkeypatch):
        # limit 1 -> pool of 4: the high score in 5th place is out of reach.
        self._wire(monkeypatch, {1: [story(str(i), i) for i in range(1, 5)] + [story("x", 999)]})
        out = lob.get_lobsters_hottest(limit=1)
        assert out[0]["short_id"] == "4"

    def test_drops_repeats_across_pages(self, monkeypatch):
        self._wire(monkeypatch, {
            1: [story(str(i)) for i in range(24)] + [story("dup", 5)],
            2: [story("dup", 5), story("z", 3)],
        })
        out = lob.get_lobsters_hottest(limit=10)
        assert [s["short_id"] for s in out].count("dup") == 1

    def test_excludes_tags_case_insensitively(self, monkeypatch):
        self._wire(monkeypatch, {1: [
            story("meta", 99, ["announce", "meta"]),
            story("rust", 10, ["rust"]),
            story("plain", 5),
        ]})
        out = lob.get_lobsters_hottest(limit=10, exclude_tags=["META"])
        assert [s["short_id"] for s in out] == ["rust", "plain"]


class TestPostedAt:
    def test_converts_offset_to_utc(self):
        assert lob.posted_at({"created_at": "2026-10-18T20:28:53.196-05:00"}) == "2026-10-19 01:28 UTC"

    @pytest.mark.parametrize("value", [None, "", "yesterday"])
    def test_unreadable_is_none(self, value):
        assert lob.posted_at({"created_at": value}) is None

    def test_missing_is_none(self):
        assert lob.posted_at({}) is None


class TestStoryToDict:
    def test_full(self):
        raw = story(
            "abc", 42, ["rust", "compilers"], title="T", comment_count=7,
            created_at="2026-10-18T12:00:00.000+00:00", url="https://x.example/post",
            comments_url="https://lobste.rs/s/abc/t", short_id_url="https://lobste.rs/s/abc",
        )
        assert lob.story_to_dict(1, raw) == {
            "rank": 1,
            "title": "T",
            "score": 42,
            "comments": 7,
            "posted": "2026-10-18 12:00 UTC",
            "url": "https://x.example/post",
            "discussion_url": "https://lobste.rs/s/abc/t",
            "tags": ["rust", "compilers"],
        }

    def test_text_post_links_to_discussion(self):
        row = lob.story_to_dict(1, story("abc", url="", comments_url="https://lobste.rs/s/abc/t"))
        assert row["url"] == row["discussion_url"] == "https://lobste.rs/s/abc/t"

    def test_defaults(self):
        row = lob.story_to_dict(2, {"short_id_url": "https://lobste.rs/s/abc"})
        assert row["title"] == "(no title)"
        assert row["score"] == 0
        assert row["comments"] == 0
        assert row["posted"] is None
        assert row["tags"] == []
        assert row["url"] == row["discussion_url"] == "https://lobste.rs/s/abc"


class TestFormatStory:
    def test_includes_tags_and_links(self):
        row = {"rank": 1, "title": "T", "score": 5, "comments": 2, "posted": "2026-10-18 12:00 UTC",
               "url": "https://x", "discussion_url": "https://lobste.rs/s/a", "tags": ["rust", "web"]}
        out = lob.format_story(row)
        assert out.splitlines()[0] == "1. T"
        assert "Tags: rust, web" in out
        assert "Discussion: https://lobste.rs/s/a" in out

    def test_no_tags(self):
        row = {"rank": 1, "title": "T", "score": 5, "comments": 2, "posted": None,
               "url": "https://x", "discussion_url": "https://y", "tags": []}
        assert "Tags: (none)" in lob.format_story(row)


class TestParseArgs:
    def test_defaults(self):
        args = lob.parse_args([])
        assert args.limit == 10
        assert args.exclude_tag == []
        assert args.json is False

    def test_repeatable_exclude_tag(self):
        args = lob.parse_args(["--exclude-tag", "meta", "--exclude-tag", "culture"])
        assert args.exclude_tag == ["meta", "culture"]


class TestMain:
    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            lob, "get_lobsters_hottest",
            lambda limit, exclude_tags: [story("a", 5, ["rust"], title="T",
                                               comments_url="https://lobste.rs/s/a")],
        )
        lob.main(["--json"])
        rows = json.loads(capsys.readouterr().out)
        assert rows[0]["rank"] == 1 and rows[0]["title"] == "T" and rows[0]["tags"] == ["rust"]

    def test_passes_limit_and_tags(self, monkeypatch, capsys):
        seen = {}
        monkeypatch.setattr(
            lob, "get_lobsters_hottest",
            lambda limit, exclude_tags: seen.update(limit=limit, tags=exclude_tags) or [],
        )
        lob.main(["--limit", "3", "--exclude-tag", "meta", "--json"])
        assert seen == {"limit": 3, "tags": ["meta"]}

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            lob, "get_lobsters_hottest",
            lambda limit, exclude_tags: [story("a", 5, title="T", url="https://x",
                                               comments_url="https://lobste.rs/s/a")],
        )
        lob.main([])
        out = capsys.readouterr().out
        assert "Fetching the hottest discussions from Lobsters" in out
        assert "1. T" in out

    @pytest.mark.parametrize("error", [requests.RequestException("down"), ValueError("down")])
    def test_errors_exit_1(self, monkeypatch, capsys, error):
        def boom(limit, exclude_tags):
            raise error

        monkeypatch.setattr(lob, "get_lobsters_hottest", boom)
        with pytest.raises(SystemExit) as exc:
            lob.main(["--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "down"}

    def test_empty_text(self, monkeypatch, capsys):
        monkeypatch.setattr(lob, "get_lobsters_hottest", lambda limit, exclude_tags: [])
        lob.main([])
        assert "No stories found." in capsys.readouterr().out

    @pytest.mark.parametrize("bad", ["0", "-1", "abc"])
    def test_invalid_limit_exits_2_before_fetch(self, monkeypatch, bad):
        def fail(limit, exclude_tags):
            raise AssertionError("should not fetch")

        monkeypatch.setattr(lob, "get_lobsters_hottest", fail)
        with pytest.raises(SystemExit) as exc:
            lob.main(["--limit", bad])
        assert exc.value.code == 2
