"""Tests for hn_thread: item ids, comment tree ranking/selection, records, rendering, and main()."""

import json

import pytest
import requests

import hn_thread as ht
from helpers import FakeResponse


def comment(item_id, text="hi", children=(), author="a", time=1704067200):
    return {
        "id": item_id,
        "type": "comment",
        "author": author,
        "text": text,
        "created_at_i": time,
        "children": list(children),
    }


def make_tree():
    """Story 1 with top-level comments 10, 20, 30 (Algolia's oldest-first order),
    a deleted leaf 40, and replies under 10."""
    return {
        "id": 1,
        "type": "story",
        "title": "Bun in Rust",
        "author": "op",
        "points": 800,
        "url": "https://example.com/post",
        "text": None,
        "created_at_i": 1704067200,
        "story_id": 1,
        "children": [
            comment(10, "first", [
                comment(11, "reply a", [comment(111, "deep")]),
                comment(12, "reply b"),
                comment(13, "reply c"),
            ]),
            comment(20, "second"),
            comment(30, "third"),
            {"id": 40, "type": "comment", "author": None, "text": None, "children": []},
        ],
    }


# Ranked `kids` lists, as the official HN API returns them.
RANKED = {1: [30, 10, 20, 40], 10: [12, 11, 13], 11: [111]}


@pytest.fixture
def ranked_api(monkeypatch):
    calls = []

    def fake_fetch_story(item_id):
        calls.append(item_id)
        return {"id": item_id, "kids": RANKED.get(item_id, [])}

    monkeypatch.setattr(ht, "fetch_story", fake_fetch_story)
    return calls


class TestParseItemId:
    @pytest.mark.parametrize("value, expected", [
        ("48843352", 48843352),
        (" 42 ", 42),
        ("https://news.ycombinator.com/item?id=48843352", 48843352),
        ("news.ycombinator.com/item?id=7", 7),
        ("https://news.ycombinator.com/item?p=2&id=99", 99),
    ])
    def test_valid(self, value, expected):
        assert ht.parse_item_id(value) == expected

    @pytest.mark.parametrize("value", ["", "abc", "https://example.com/?id=5", "-3"])
    def test_invalid(self, value):
        with pytest.raises(ValueError):
            ht.parse_item_id(value)


class TestFetchTree:
    def test_success_uses_long_timeout(self, monkeypatch):
        captured = {}

        def fake_get(url, params, timeout):
            captured.update(url=url, timeout=timeout)
            return FakeResponse(json_data={"id": 5})

        monkeypatch.setattr(ht.requests, "get", fake_get)
        assert ht.fetch_tree(5) == {"id": 5}
        assert captured == {"url": "https://hn.algolia.com/api/v1/items/5",
                            "timeout": ht.ITEM_TIMEOUT}

    def test_404_is_none(self, monkeypatch):
        error = requests.HTTPError("404 Client Error")
        error.response = FakeResponse(status_code=404)
        response = FakeResponse(status_code=404, json_data={"error": "Not Found"},
                                raise_for_status=error)
        monkeypatch.setattr(ht.requests, "get", lambda url, params, timeout: response)
        assert ht.fetch_tree(5) is None

    def test_other_errors_raise(self, monkeypatch):
        error = requests.HTTPError("503 Server Error")
        error.response = FakeResponse(status_code=503)
        response = FakeResponse(status_code=503, raise_for_status=error)
        monkeypatch.setattr(ht.requests, "get", lambda url, params, timeout: response)
        with pytest.raises(requests.HTTPError):
            ht.fetch_tree(5)


class TestTreeHelpers:
    def test_count_comments(self):
        assert ht.count_comments(make_tree()) == 8
        assert ht.count_comments({"children": []}) == 0
        assert ht.count_comments({}) == 0

    def test_is_empty(self):
        assert ht.is_empty({"text": None, "children": []})
        assert not ht.is_empty({"text": None, "children": [comment(1)]})
        assert not ht.is_empty(comment(1))

    def test_ranked_children_follows_kids_and_drops_empty(self):
        ids = [c["id"] for c in ht.ranked_children(make_tree(), RANKED[1])]
        assert ids == [30, 10, 20]

    def test_ranked_children_unknown_go_last(self):
        ids = [c["id"] for c in ht.ranked_children(make_tree(), [20])]
        assert ids == [20, 10, 30]

    def test_ranked_children_without_kids_keeps_algolia_order(self):
        ids = [c["id"] for c in ht.ranked_children(make_tree(), None)]
        assert ids == [10, 20, 30]

    def test_fetch_kids(self, monkeypatch):
        monkeypatch.setattr(
            ht, "fetch_story",
            lambda item_id: None if item_id == 2 else {"kids": [item_id * 10]} if item_id == 1 else {},
        )
        assert ht.fetch_kids([1, 2, 3]) == {1: [10], 2: None, 3: []}


def ids(trees):
    return [(node["id"], [ids_child for ids_child in ids(children)]) for node, _, children in trees]


class TestSelectComments:
    def test_defaults_rank_and_limit_replies(self, ranked_api):
        trees, ranked = ht.select_comments(make_tree(), top=20, replies=2, depth=2)
        assert ranked is True
        assert ids(trees) == [(30, []), (10, [(12, []), (11, [])]), (20, [])]
        # ranked order fetched for the story, then only for comments with replies
        assert ranked_api == [1, 10]

    def test_top_limits_top_level(self, ranked_api):
        trees, _ = ht.select_comments(make_tree(), top=1, replies=3, depth=3)
        assert ids(trees) == [(30, [])]

    def test_depth_one_is_top_level_only(self, ranked_api):
        trees, _ = ht.select_comments(make_tree(), top=5, replies=3, depth=1)
        assert ids(trees) == [(30, []), (10, []), (20, [])]
        assert ranked_api == [1]

    def test_replies_zero(self, ranked_api):
        trees, _ = ht.select_comments(make_tree(), top=5, replies=0, depth=3)
        assert ids(trees) == [(30, []), (10, []), (20, [])]

    def test_depth_three(self, ranked_api):
        trees, _ = ht.select_comments(make_tree(), top=5, replies=3, depth=3)
        assert ids(trees)[1] == (10, [(12, []), (11, [(111, [])]), (13, [])])
        assert ranked_api == [1, 10, 11]

    def test_levels_recorded(self, ranked_api):
        trees, _ = ht.select_comments(make_tree(), top=5, replies=3, depth=3)
        node, level, children = trees[1]
        assert level == 1
        assert children[1][1] == 2
        assert children[1][2][0][1] == 3

    def test_fallback_to_oldest_first(self, monkeypatch):
        monkeypatch.setattr(ht, "fetch_story", lambda item_id: None)
        trees, ranked = ht.select_comments(make_tree(), top=5, replies=1, depth=2)
        assert ranked is False
        assert ids(trees) == [(10, [(11, [])]), (20, []), (30, [])]

    def test_partial_fallback_marks_unranked(self, monkeypatch):
        monkeypatch.setattr(
            ht, "fetch_story",
            lambda item_id: {"kids": RANKED[1]} if item_id == 1 else None,
        )
        trees, ranked = ht.select_comments(make_tree(), top=5, replies=1, depth=2)
        assert ranked is False
        assert ids(trees)[1] == (10, [(11, [])])


class TestRecords:
    def test_comment_to_dict(self, ranked_api):
        trees, _ = ht.select_comments(make_tree(), top=5, replies=1, depth=2)
        row = ht.comment_to_dict(trees[1])
        assert row == {
            "id": 10,
            "author": "a",
            "posted": "2024-01-01 00:00 UTC",
            "depth": 1,
            "url": "https://news.ycombinator.com/item?id=10",
            "text": "first",
            "reply_count": 3,
            "total_replies": 4,
            "replies": [{
                "id": 12,
                "author": "a",
                "posted": "2024-01-01 00:00 UTC",
                "depth": 2,
                "url": "https://news.ycombinator.com/item?id=12",
                "text": "reply b",
                "reply_count": 0,
                "total_replies": 0,
                "replies": [],
            }],
        }

    def test_deleted_comment_with_replies(self):
        node = {"id": 5, "author": None, "text": None, "children": [comment(6)]}
        row = ht.comment_to_dict((node, 1, []))
        assert row["author"] == "[deleted]"
        assert row["text"] == "[deleted]"
        assert row["reply_count"] == 1

    def test_text_cut(self):
        row = ht.comment_to_dict((comment(5, "abcdefgh"), 1, []), max_chars=3)
        assert row["text"] == "abc..."

    def test_thread_to_dict(self, ranked_api):
        root = make_tree()
        trees, ranked = ht.select_comments(root, top=2, replies=1, depth=2)
        thread = ht.thread_to_dict(root, trees, ranked)
        assert {k: v for k, v in thread.items() if k != "comments"} == {
            "id": 1,
            "type": "story",
            "title": "Bun in Rust",
            "author": "op",
            "posted": "2024-01-01 00:00 UTC",
            "score": 800,
            "url": "https://example.com/post",
            "discussion_url": "https://news.ycombinator.com/item?id=1",
            "story_url": "https://news.ycombinator.com/item?id=1",
            "text": None,
            "total_comments": 8,
            "top_level_comments": 3,
            "shown_comments": 3,
            "ranked": True,
        }
        assert [c["id"] for c in thread["comments"]] == [30, 10]

    def test_self_post_and_comment_root(self):
        root = comment(48844834, "root text", [comment(2)])
        root["story_id"] = 48843352
        thread = ht.thread_to_dict(root, [], True)
        assert thread["type"] == "comment"
        assert thread["url"] == thread["discussion_url"] == "https://news.ycombinator.com/item?id=48844834"
        assert thread["story_url"] == "https://news.ycombinator.com/item?id=48843352"
        assert thread["text"] == "root text"
        assert thread["shown_comments"] == 0


class TestFormatThread:
    def _thread(self, ranked_api, **kwargs):
        root = make_tree()
        trees, ranked = ht.select_comments(root, **kwargs)
        return ht.thread_to_dict(root, trees, ranked)

    def test_story_report(self, ranked_api):
        out = ht.format_thread(self._thread(ranked_api, top=2, replies=1, depth=2))
        assert out.splitlines()[0] == "Bun in Rust"
        assert "Score: 800  |  Comments: 8  |  Posted: 2024-01-01 00:00 UTC  |  By: op" in out
        assert "Showing 3 of 8 comments (3 top-level), in HN's ranked order." in out
        assert "   1. a | 2024-01-01 00:00 UTC | https://news.ycombinator.com/item?id=30" in out
        assert "      2.1. a | 2024-01-01 00:00 UTC | https://news.ycombinator.com/item?id=12" in out
        assert "(+2 more replies, 4 comments below this one in all)" in out

    def test_singular_hidden_counts(self):
        row = {"id": 1, "author": "a", "posted": "p", "depth": 1, "url": "u", "text": "t",
               "reply_count": 1, "total_replies": 1, "replies": []}
        assert "(+1 more reply, 1 comment below this one in all)" in ht.format_comment(row, "1.")

    def test_unranked_note(self, monkeypatch):
        monkeypatch.setattr(ht, "fetch_story", lambda item_id: None)
        root = make_tree()
        trees, ranked = ht.select_comments(root, top=1, replies=0, depth=1)
        out = ht.format_thread(ht.thread_to_dict(root, trees, ranked))
        assert "partly oldest-first (ranked order unavailable)" in out

    def test_comment_root(self):
        root = comment(5, "root text", [comment(6)])
        root["story_id"] = 4
        out = ht.format_thread(ht.thread_to_dict(root, [], True))
        assert out.splitlines()[0] == "Comment by a | 2024-01-01 00:00 UTC"
        assert "Story: https://news.ycombinator.com/item?id=4" in out
        assert "(1 direct replies)" in out
        assert "\n   root text" in out


class TestParseArgs:
    def test_defaults(self):
        args = ht.parse_args(["48843352"])
        assert args.item == 48843352
        assert args.top == ht.TOP_COMMENTS
        assert args.replies == ht.REPLIES_PER_COMMENT
        assert args.depth == ht.DEPTH
        assert args.max_chars == ht.TEXT_CHARS
        assert args.json is False

    def test_flags_and_url(self):
        args = ht.parse_args([
            "https://news.ycombinator.com/item?id=7", "--top", "200", "--replies", "0",
            "--depth", "10", "--max-chars", "0", "--json",
        ])
        assert (args.item, args.top, args.replies, args.depth, args.max_chars, args.json) == (
            7, 200, 0, 10, 0, True
        )

    @pytest.mark.parametrize("argv", [
        ["abc"],
        ["1", "--top", "0"],
        ["1", "--top", str(ht.MAX_TOP_COMMENTS + 1)],
        ["1", "--replies", "-1"],
        ["1", "--depth", "0"],
        ["1", "--depth", str(ht.MAX_DEPTH + 1)],
        ["1", "--max-chars", "-1"],
    ])
    def test_invalid_rejected(self, argv):
        with pytest.raises(SystemExit) as exc:
            ht.parse_args(argv)
        assert exc.value.code == 2


class TestMain:
    def test_json_output(self, monkeypatch, ranked_api, capsys):
        monkeypatch.setattr(ht, "fetch_tree", lambda item_id: make_tree())
        ht.main(["1", "--top", "2", "--replies", "1", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["title"] == "Bun in Rust"
        assert payload["shown_comments"] == 3
        assert payload["comments"][1]["replies"][0]["id"] == 12

    def test_text_output(self, monkeypatch, ranked_api, capsys):
        monkeypatch.setattr(ht, "fetch_tree", lambda item_id: make_tree())
        ht.main(["https://news.ycombinator.com/item?id=1", "--depth", "1"])
        out = capsys.readouterr().out
        assert "Reading Hacker News thread 1..." in out
        assert "Showing 3 of 8 comments" in out

    def test_missing_item_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(ht, "fetch_tree", lambda item_id: None)
        with pytest.raises(SystemExit) as exc:
            ht.main(["999", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "No Hacker News item with id 999."}

    def test_request_error_exits_1(self, monkeypatch, capsys):
        def boom(item_id):
            raise requests.ConnectionError("network down")

        monkeypatch.setattr(ht, "fetch_tree", boom)
        with pytest.raises(SystemExit) as exc:
            ht.main(["1"])
        assert exc.value.code == 1
        assert "Error: network down" in capsys.readouterr().err
