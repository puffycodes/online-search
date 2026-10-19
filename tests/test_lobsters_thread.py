"""Tests for lobsters_thread: story ids, fetching, nesting and pruning comments, records, formatting, and main()."""

import json

import pytest
import requests

import lobsters_thread as lt
from helpers import FakeResponse


def comment(short_id, parent=None, depth=0, **extra):
    return {
        "short_id": short_id,
        "parent_comment": parent,
        "depth": depth,
        "commenting_user": f"user-{short_id}",
        "comment_plain": f"text {short_id}",
        "score": 1,
        "created_at": "2026-10-18T07:44:28.817-05:00",
        "url": f"https://lobste.rs/s/abc/t#c_{short_id}",
        **extra,
    }


def story(comments=(), **extra):
    return {
        "short_id": "abc",
        "title": "T",
        "submitter_user": "sub",
        "created_at": "2026-10-18T12:00:00.000+00:00",
        "score": 42,
        "url": "https://x.example/post",
        "comments_url": "https://lobste.rs/s/abc/t",
        "tags": ["rust"],
        "description_plain": "",
        "comment_count": len(comments),
        "comments": list(comments),
        **extra,
    }


# a1 (b1 (c1), b2, b3), a2, a3
THREAD = [
    comment("a1"),
    comment("b1", "a1", 1),
    comment("c1", "b1", 2),
    comment("b2", "a1", 1),
    comment("b3", "a1", 1),
    comment("a2"),
    comment("a3"),
]


class TestParseStoryId:
    @pytest.mark.parametrize("value,expected", [
        ("ggpwfi", "ggpwfi"),
        ("  ggpwfi ", "ggpwfi"),
        ("https://lobste.rs/s/ggpwfi", "ggpwfi"),
        ("https://lobste.rs/s/ggpwfi/it_s_enough_vibecoding", "ggpwfi"),
        ("lobste.rs/s/ggpwfi/slug#c_n3ahgg", "ggpwfi"),
    ])
    def test_accepts(self, value, expected):
        assert lt.parse_story_id(value) == expected

    @pytest.mark.parametrize("value", ["https://example.com/s/abc", "https://lobste.rs/c/n3ahgg", "a b", ""])
    def test_rejects(self, value):
        with pytest.raises(ValueError, match="expected a Lobsters story id"):
            lt.parse_story_id(value)


class TestFetchStory:
    def test_url_headers_timeout(self, monkeypatch):
        calls = []

        def fake_get(url, headers=None, timeout=None):
            calls.append((url, headers, timeout))
            return FakeResponse(json_data=story())

        monkeypatch.setattr(lt.requests, "get", fake_get)
        assert lt.fetch_story("abc")["short_id"] == "abc"
        assert calls == [("https://lobste.rs/s/abc.json", lt.HEADERS, lt.STORY_TIMEOUT)]

    def test_404_is_none(self, monkeypatch):
        monkeypatch.setattr(lt.requests, "get", lambda url, **k: FakeResponse(status_code=404))
        assert lt.fetch_story("zzz") is None

    def test_other_error_raises(self, monkeypatch):
        error = requests.HTTPError("500 Server Error")
        monkeypatch.setattr(
            lt.requests, "get",
            lambda url, **k: FakeResponse(status_code=500, raise_for_status=error),
        )
        with pytest.raises(requests.HTTPError):
            lt.fetch_story("abc")

    def test_non_object_raises(self, monkeypatch):
        monkeypatch.setattr(lt.requests, "get", lambda url, **k: FakeResponse(json_data=[]))
        with pytest.raises(ValueError, match="expected an object"):
            lt.fetch_story("abc")


class TestHelpers:
    def test_username(self):
        assert lt.username("alice") == "alice"
        assert lt.username({"username": "bob"}) == "bob"
        assert lt.username(None) is None

    def test_clip(self):
        assert lt.clip(None) is None
        assert lt.clip("  \r\n ") is None
        assert lt.clip("a\r\n\r\n\r\n\r\nb") == "a\n\nb"
        assert lt.clip("abcdef", 3) == "abc..."
        assert lt.clip("abcdef", 0) == "abcdef"

    def test_comment_text(self):
        assert lt.comment_text(comment("a", is_deleted=True)) == "[deleted]"
        assert lt.comment_text(comment("a", is_moderated=True)) == "[removed by a moderator]"
        assert lt.comment_text(comment("a", comment_plain="")) == "[empty]"
        assert lt.comment_text(comment("a"), 3) == "tex..."


class TestBuildTree:
    def test_nests_in_list_order(self):
        roots = lt.build_tree(THREAD)
        assert [n["comment"]["short_id"] for n in roots] == ["a1", "a2", "a3"]
        assert [n["comment"]["short_id"] for n in roots[0]["children"]] == ["b1", "b2", "b3"]
        assert roots[0]["children"][0]["children"][0]["comment"]["short_id"] == "c1"
        assert lt.count_comments(roots[0]) == 4

    def test_orphan_goes_to_top(self):
        roots = lt.build_tree([comment("x", "missing", 1)])
        assert [n["comment"]["short_id"] for n in roots] == ["x"]

    def test_prune_drops_removed_leaves_at_any_depth(self):
        roots = lt.prune(lt.build_tree([
            comment("a1", is_deleted=True),
            comment("b1", "a1", 1, is_moderated=True),   # removed leaf -> a1 becomes a leaf too
            comment("a2", is_deleted=True),
            comment("b2", "a2", 1),                      # live reply keeps a2
            comment("a3"),
        ]))
        assert [n["comment"]["short_id"] for n in roots] == ["a2", "a3"]
        assert [n["comment"]["short_id"] for n in roots[0]["children"]] == ["b2"]


class TestThreadToDict:
    def test_story_fields(self):
        thread = lt.thread_to_dict(story(THREAD, description_plain="Hello"))
        assert {k: thread[k] for k in ("id", "title", "author", "posted", "score", "url",
                                       "discussion_url", "tags", "text")} == {
            "id": "abc",
            "title": "T",
            "author": "sub",
            "posted": "2026-10-18 12:00 UTC",
            "score": 42,
            "url": "https://x.example/post",
            "discussion_url": "https://lobste.rs/s/abc/t",
            "tags": ["rust"],
            "text": "Hello",
        }

    def test_text_post_links_to_discussion(self):
        thread = lt.thread_to_dict(story(url=""))
        assert thread["url"] == thread["discussion_url"] == "https://lobste.rs/s/abc/t"
        assert thread["text"] is None

    def test_default_limits(self):
        thread = lt.thread_to_dict(story(THREAD))
        assert thread["total_comments"] == 7
        assert thread["top_level_comments"] == 3
        # depth 2: a1 + 3 replies (c1 is a 3rd level), a2, a3
        assert thread["shown_comments"] == 6
        first = thread["comments"][0]
        assert [r["id"] for r in first["replies"]] == ["b1", "b2", "b3"]
        assert first["replies"][0]["replies"] == []
        assert first["replies"][0]["reply_count"] == 1

    def test_top_replies_depth(self):
        thread = lt.thread_to_dict(story(THREAD), top=1, replies=1, depth=3)
        assert [c["id"] for c in thread["comments"]] == ["a1"]
        first = thread["comments"][0]
        assert [r["id"] for r in first["replies"]] == ["b1"]
        assert [r["id"] for r in first["replies"][0]["replies"]] == ["c1"]
        assert thread["shown_comments"] == 3

    def test_depth_one_is_top_level_only(self):
        thread = lt.thread_to_dict(story(THREAD), depth=1)
        assert all(c["replies"] == [] for c in thread["comments"])

    def test_comment_record(self):
        row = lt.thread_to_dict(story(THREAD), max_chars=4)["comments"][0]
        assert row == {
            "id": "a1",
            "author": "user-a1",
            "posted": "2026-10-18 12:44 UTC",
            "depth": 1,
            "score": 1,
            "url": "https://lobste.rs/s/abc/t#c_a1",
            "text": "text...",
            "reply_count": 3,
            "total_replies": 4,
            "replies": row["replies"],
        }
        assert row["replies"][0]["depth"] == 2

    def test_total_falls_back_to_counting(self):
        thread = lt.thread_to_dict(story(THREAD, comment_count=None))
        assert thread["total_comments"] == 7


class TestFormatThread:
    def test_report(self):
        out = lt.format_thread(lt.thread_to_dict(story(THREAD, description_plain="Hello"), top=1, replies=1))
        assert out.splitlines()[0] == "T"
        assert "By: sub" in out
        assert "Tags: rust" in out
        assert "   Hello" in out
        assert "Showing 2 of 7 comments (3 top-level), in Lobsters' order." in out
        assert "   1. user-a1 | 1 points | 2026-10-18 12:44 UTC | https://lobste.rs/s/abc/t#c_a1" in out
        assert "      1.1. user-b1 |" in out
        assert "(+2 more replies, 4 comments below this one in all)" in out
        # b1's own reply is beyond the depth: singular wording
        assert "(+1 more reply, 1 comment below this one in all)" in out


class TestParseArgs:
    def test_defaults(self):
        args = lt.parse_args(["https://lobste.rs/s/abc/t"])
        assert (args.story, args.top, args.replies, args.depth, args.max_chars, args.json) == (
            "abc", 20, 3, 2, 600, False
        )

    @pytest.mark.parametrize("argv", [
        ["https://example.com/x"],
        ["abc", "--top", "0"],
        ["abc", "--top", "201"],
        ["abc", "--replies", "-1"],
        ["abc", "--depth", "11"],
        ["abc", "--max-chars", "x"],
    ])
    def test_invalid_exits_2(self, argv):
        with pytest.raises(SystemExit) as exc:
            lt.parse_args(argv)
        assert exc.value.code == 2


class TestMain:
    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(lt, "fetch_story", lambda story_id: story(THREAD))
        lt.main(["abc", "--json", "--top", "1"])
        thread = json.loads(capsys.readouterr().out)
        assert thread["id"] == "abc" and len(thread["comments"]) == 1

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(lt, "fetch_story", lambda story_id: story(THREAD))
        lt.main(["abc"])
        out = capsys.readouterr().out
        assert "Reading Lobsters thread abc..." in out
        assert "Showing 6 of 7 comments" in out

    def test_missing_story_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(lt, "fetch_story", lambda story_id: None)
        with pytest.raises(SystemExit) as exc:
            lt.main(["zzz", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "No Lobsters story with id zzz."}

    @pytest.mark.parametrize("error", [requests.RequestException("down"), ValueError("down")])
    def test_errors_exit_1(self, monkeypatch, capsys, error):
        def boom(story_id):
            raise error

        monkeypatch.setattr(lt, "fetch_story", boom)
        with pytest.raises(SystemExit) as exc:
            lt.main(["abc", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "down"}

    def test_invalid_story_exits_2_before_fetch(self, monkeypatch):
        def fail(story_id):
            raise AssertionError("should not fetch")

        monkeypatch.setattr(lt, "fetch_story", fail)
        with pytest.raises(SystemExit) as exc:
            lt.main(["https://example.com/x"])
        assert exc.value.code == 2
