"""Tests for hottest_tech_discussions: story records, sources, sections, and main()."""

import json

import pytest
import requests

import hottest_tech_discussions as htd

HN_STORY = {"id": 1, "title": "HN story", "score": 500, "descendants": 2,
            "time": 1704067200, "url": "http://x"}
LOBSTERS_STORY = {"short_id": "abc", "title": "Lobsters story", "score": 40, "comment_count": 7,
                  "created_at": "2026-10-18T12:00:00.000+00:00", "url": "https://y",
                  "comments_url": "https://lobste.rs/s/abc/t", "tags": ["rust"]}


def wire(monkeypatch, hn=(), lobsters=(), seen=None):
    """Patch both sources' fetches, recording their arguments in `seen`."""
    seen = seen if seen is not None else {}

    def fake_hn(limit):
        seen["hn"] = limit
        return list(hn)

    def fake_lobsters(limit, exclude_tags=()):
        seen["lobsters"] = (limit, list(exclude_tags))
        return list(lobsters)

    monkeypatch.setattr(htd, "get_hottest_tech_discussions", fake_hn)
    monkeypatch.setattr(htd.lobsters, "fetch_hottest", fake_lobsters)
    return seen


class TestGetHottestTechDiscussions:
    def test_is_hacker_news_only(self, monkeypatch):
        monkeypatch.setattr(htd.hn, "fetch_hottest", lambda limit: [{"id": limit}])
        assert htd.get_hottest_tech_discussions(limit=3) == [{"id": 3}]


class TestStoryToDict:
    def test_story_to_dict_full(self):
        story = {"title": "T", "score": 5, "descendants": 3, "time": 1704067200,
                 "url": "http://x", "id": 9}
        assert htd.story_to_dict(1, story) == {
            "rank": 1,
            "title": "T",
            "score": 5,
            "comments": 3,
            "posted": "2024-01-01 00:00 UTC",
            "url": "http://x",
            "discussion_url": "https://news.ycombinator.com/item?id=9",
            "tags": [],
            "source": "hn",
        }

    def test_story_to_dict_defaults(self):
        row = htd.story_to_dict(2, {"id": 7})
        assert row["title"] == "(no title)"
        assert row["score"] == 0
        assert row["comments"] == 0
        assert row["url"] == row["discussion_url"] == "https://news.ycombinator.com/item?id=7"


class TestLobstersStoryToDict:
    def test_full(self):
        raw = dict(LOBSTERS_STORY, tags=["rust", "compilers"])
        assert htd.lobsters_story_to_dict(1, raw) == {
            "rank": 1,
            "title": "Lobsters story",
            "score": 40,
            "comments": 7,
            "posted": "2026-10-18 12:00 UTC",
            "url": "https://y",
            "discussion_url": "https://lobste.rs/s/abc/t",
            "tags": ["rust", "compilers"],
            "source": "lobsters",
        }

    def test_text_post_links_to_discussion(self):
        row = htd.lobsters_story_to_dict(1, {"url": "", "comments_url": "https://lobste.rs/s/abc/t"})
        assert row["url"] == row["discussion_url"] == "https://lobste.rs/s/abc/t"

    def test_defaults(self):
        row = htd.lobsters_story_to_dict(2, {"short_id_url": "https://lobste.rs/s/abc"})
        assert row["title"] == "(no title)"
        assert row["score"] == 0
        assert row["comments"] == 0
        assert row["posted"] is None
        assert row["tags"] == []
        assert row["url"] == row["discussion_url"] == "https://lobste.rs/s/abc"


class TestFormatStory:
    def test_hacker_news_has_no_tags_line(self):
        out = htd.format_story(htd.story_to_dict(1, HN_STORY))
        assert out.splitlines()[0] == "1. HN story"
        assert "Tags:" not in out
        assert "Discussion: https://news.ycombinator.com/item?id=1" in out

    def test_lobsters_shows_tags(self):
        out = htd.format_story(htd.lobsters_story_to_dict(1, dict(LOBSTERS_STORY, tags=["rust", "web"])))
        assert "Tags: rust, web" in out

    def test_lobsters_no_tags(self):
        out = htd.format_story(htd.lobsters_story_to_dict(1, dict(LOBSTERS_STORY, tags=[])))
        assert "Tags: (none)" in out


class TestParseArgs:
    def test_defaults(self):
        args = htd.parse_args([])
        assert args.source == ["hn"]
        assert args.limit == 10
        assert args.exclude_tag == []
        assert args.json is False

    def test_sources_in_fixed_order_and_repeats_count_once(self):
        args = htd.parse_args(["--source", "lobsters", "--source", "hn", "--source", "lobsters"])
        assert args.source == ["hn", "lobsters"]

    def test_repeatable_exclude_tag_with_lobsters(self):
        args = htd.parse_args(["--source", "lobsters", "--exclude-tag", "meta", "--exclude-tag", "culture"])
        assert args.exclude_tag == ["meta", "culture"]

    @pytest.mark.parametrize("argv", [
        ["--source", "reddit"],
        ["--exclude-tag", "meta"],
        ["--source", "hn", "--exclude-tag", "meta"],
        ["--limit", "0"],
        ["--limit", "-1"],
        ["--limit", "abc"],
    ])
    def test_invalid_options_exit_2(self, argv):
        with pytest.raises(SystemExit) as exc:
            htd.parse_args(argv)
        assert exc.value.code == 2


class TestGetRows:
    def test_only_the_asked_sources(self, monkeypatch):
        seen = wire(monkeypatch, hn=[HN_STORY], lobsters=[LOBSTERS_STORY])
        rows = htd.get_rows(["lobsters"], limit=5, exclude_tags=["meta"])
        assert list(rows) == ["lobsters"]
        assert seen == {"lobsters": (5, ["meta"])}

    def test_rank_restarts_per_source(self, monkeypatch):
        wire(monkeypatch, hn=[HN_STORY, dict(HN_STORY, id=2)], lobsters=[LOBSTERS_STORY])
        rows = htd.get_rows(["hn", "lobsters"])
        assert [r["rank"] for r in rows["hn"]] == [1, 2]
        assert [r["rank"] for r in rows["lobsters"]] == [1]

    @pytest.mark.parametrize("error", [requests.RequestException("down"), ValueError("down")])
    def test_failure_names_the_source(self, monkeypatch, error):
        wire(monkeypatch, hn=[HN_STORY])

        def boom(limit, exclude_tags=()):
            raise error

        monkeypatch.setattr(htd.lobsters, "fetch_hottest", boom)
        with pytest.raises(htd.SourceError, match="^Lobsters: down$"):
            htd.get_rows(["hn", "lobsters"])


class TestMain:
    def test_json_output_hacker_news_by_default(self, monkeypatch, capsys):
        seen = wire(monkeypatch, hn=[HN_STORY], lobsters=[LOBSTERS_STORY])
        htd.main(["--json"])
        rows = json.loads(capsys.readouterr().out)
        assert [(r["rank"], r["title"], r["source"], r["tags"]) for r in rows] == [(1, "HN story", "hn", [])]
        assert seen == {"hn": 10}

    def test_json_output_grouped_by_source(self, monkeypatch, capsys):
        seen = wire(monkeypatch, hn=[HN_STORY], lobsters=[LOBSTERS_STORY, dict(LOBSTERS_STORY, short_id="d")])
        htd.main(["--source", "lobsters", "--source", "hn", "--limit", "3", "--exclude-tag", "meta", "--json"])
        rows = json.loads(capsys.readouterr().out)
        assert [(r["source"], r["rank"]) for r in rows] == [("hn", 1), ("lobsters", 1), ("lobsters", 2)]
        assert seen == {"hn": 3, "lobsters": (3, ["meta"])}

    def test_text_hacker_news_alone_has_no_heading(self, monkeypatch, capsys):
        wire(monkeypatch, hn=[HN_STORY])
        htd.main([])
        out = capsys.readouterr().out
        assert out.startswith("Fetching the hottest technology discussions from Hacker News...\n\n1. HN story\n")
        assert "=====" not in out

    def test_text_headings_per_source(self, monkeypatch, capsys):
        wire(monkeypatch, hn=[HN_STORY], lobsters=[LOBSTERS_STORY])
        htd.main(["--source", "hn", "--source", "lobsters"])
        out = capsys.readouterr().out
        assert "from Hacker News and Lobsters..." in out
        assert "Hacker News\n===========\n\n1. HN story" in out
        assert "Lobsters\n========\n\n1. Lobsters story" in out
        assert out.index("Hacker News\n") < out.index("Lobsters\n")
        assert "Tags: rust" in out

    def test_text_lobsters_alone_has_a_heading(self, monkeypatch, capsys):
        wire(monkeypatch, lobsters=[LOBSTERS_STORY])
        htd.main(["--source", "lobsters"])
        out = capsys.readouterr().out
        assert "from Lobsters..." in out
        assert "Lobsters\n========\n" in out

    def test_empty_text(self, monkeypatch, capsys):
        wire(monkeypatch)
        htd.main([])
        assert "No stories found." in capsys.readouterr().out

    def test_empty_source_says_so_in_its_section(self, monkeypatch, capsys):
        wire(monkeypatch, hn=[HN_STORY])
        htd.main(["--source", "hn", "--source", "lobsters"])
        out = capsys.readouterr().out
        assert out.split("Lobsters\n========\n")[1].strip() == "No stories found."

    def test_hacker_news_error_exits_1(self, monkeypatch, capsys):
        def boom(limit):
            raise requests.RequestException("down")

        monkeypatch.setattr(htd, "get_hottest_tech_discussions", boom)
        with pytest.raises(SystemExit) as exc:
            htd.main(["--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "Hacker News: down"}

    def test_any_failed_source_fails_with_no_partial_output(self, monkeypatch, capsys):
        wire(monkeypatch, hn=[HN_STORY])

        def boom(limit, exclude_tags=()):
            raise ValueError("unexpected response")

        monkeypatch.setattr(htd.lobsters, "fetch_hottest", boom)
        with pytest.raises(SystemExit) as exc:
            htd.main(["--source", "hn", "--source", "lobsters", "--json"])
        captured = capsys.readouterr()
        assert exc.value.code == 1
        assert captured.out == ""
        assert json.loads(captured.err) == {"error": "Lobsters: unexpected response"}

    @pytest.mark.parametrize("argv", [["--limit", "0"], ["--exclude-tag", "meta"], ["--source", "reddit"]])
    def test_invalid_options_exit_2_before_fetch(self, monkeypatch, argv):
        def fail(*args, **kwargs):
            raise AssertionError("should not fetch")

        monkeypatch.setattr(htd, "get_hottest_tech_discussions", fail)
        monkeypatch.setattr(htd.lobsters, "fetch_hottest", fail)
        with pytest.raises(SystemExit) as exc:
            htd.main(argv)
        assert exc.value.code == 2
