"""Tests for stock_tech_buzz_agent: name normalisation, title matching, aggregation, and main()."""

import json

import pytest
import requests

import stock_tech_buzz_agent as agent


class TestNormalizeCompanyName:
    @pytest.mark.parametrize("raw,expected", [
        ("NVIDIA Corporation", "NVIDIA"),
        ("Apple Inc.", "Apple"),
        ("Nu Holdings Ltd.", "Nu Holdings"),
        ("Ford Motor Company", "Ford Motor"),
        ("APPLE INC", "APPLE"),
        ("Berkshire Hathaway", "Berkshire Hathaway"),
        ("  Tesla, Inc.  ", "Tesla"),
    ])
    def test_strips_one_outer_suffix(self, raw, expected):
        assert agent.normalize_company_name(raw) == expected


class TestStockMentionsInTitle:
    def test_symbol_whole_word_match(self):
        assert agent.stock_mentions_in_title({"symbol": "NVDA"}, "NVDA earnings beat") is True

    def test_symbol_match_is_case_sensitive(self):
        quote = {"symbol": "NVDA", "shortName": "NVIDIA"}
        assert agent.stock_mentions_in_title(quote, "the nvda rumor") is False

    def test_ambiguous_symbol_not_matched(self):
        assert agent.stock_mentions_in_title({"symbol": "AI", "shortName": "C3.ai"},
                                             "AI is everywhere") is False

    def test_company_name_match_case_insensitive(self):
        quote = {"symbol": "NVDA", "shortName": "NVIDIA Corporation"}
        assert agent.stock_mentions_in_title(quote, "Why nvidia keeps winning") is True

    def test_no_substring_false_positive(self):
        quote = {"symbol": "XOM", "shortName": "Exxon"}
        assert agent.stock_mentions_in_title(quote, "Exxonmobil posts profit") is False

    def test_short_name_below_three_chars_skipped(self):
        assert agent.stock_mentions_in_title({"symbol": "GO", "shortName": "GO"},
                                             "GO GO GO") is False

    def test_no_match(self):
        assert agent.stock_mentions_in_title({"symbol": "TSLA", "shortName": "Tesla"},
                                             "Apple ships new laptop") is False


class TestGetTopVolumeStocks:
    def test_dedupes_across_exchanges(self, monkeypatch):
        by_exchange = {
            "nyse": [{"symbol": "AAA"}, {"symbol": "BBB"}],
            "nasdaq": [{"symbol": "AAA"}, {"symbol": "CCC"}],
        }
        monkeypatch.setattr(agent.market, "get_movers",
                            lambda ex, metric, limit: list(by_exchange[ex]))
        stocks = agent.get_top_volume_stocks(limit_per_exchange=5)
        assert [s["symbol"] for s in stocks] == ["AAA", "BBB", "CCC"]
        assert stocks[0]["_exchange"] == "nyse"
        assert stocks[2]["_exchange"] == "nasdaq"


class TestFindStockBuzz:
    def test_matches_stock_to_discussion(self, monkeypatch):
        monkeypatch.setattr(agent, "get_top_volume_stocks",
                            lambda limit_per_exchange: [
                                {"symbol": "NVDA", "shortName": "NVIDIA", "_exchange": "nasdaq"}])
        monkeypatch.setattr(agent.hn, "get_hottest_tech_discussions",
                            lambda limit: [{"title": "NVDA soars on earnings", "score": 100},
                                           {"title": "Rust 2.0 released", "score": 90}])
        results, stocks, discussions = agent.find_stock_buzz()
        assert len(results) == 1
        assert results[0]["stock"]["symbol"] == "NVDA"
        assert len(results[0]["discussions"]) == 1

    def test_no_overlap(self, monkeypatch):
        monkeypatch.setattr(agent, "get_top_volume_stocks",
                            lambda limit_per_exchange: [
                                {"symbol": "TSLA", "shortName": "Tesla", "_exchange": "nasdaq"}])
        monkeypatch.setattr(agent.hn, "get_hottest_tech_discussions",
                            lambda limit: [{"title": "Apple ships laptop", "score": 10}])
        results, _, _ = agent.find_stock_buzz()
        assert results == []


class TestResultToDict:
    def test_shape(self):
        result = {
            "stock": {"symbol": "NVDA", "shortName": "NVIDIA", "_exchange": "nasdaq",
                      "regularMarketVolume": 5, "regularMarketPrice": 1.0,
                      "regularMarketChangePercent": 2.0},
            "discussions": [{"title": "T", "score": 3, "descendants": 4, "id": 9}],
        }
        row = agent.result_to_dict(result)
        assert row["symbol"] == "NVDA"
        assert row["exchange"] == "NASDAQ"
        assert row["discussions"][0]["discussion_url"] == "https://news.ycombinator.com/item?id=9"


class TestMain:
    def test_json_no_overlap(self, monkeypatch, capsys):
        monkeypatch.setattr(agent, "find_stock_buzz", lambda **k: ([], [1, 2], [3, 4]))
        agent.main(["--json"])
        assert json.loads(capsys.readouterr().out) == []

    def test_error_exits(self, monkeypatch, capsys):
        def boom(**k):
            raise requests.RequestException("down")

        monkeypatch.setattr(agent, "find_stock_buzz", boom)
        with pytest.raises(SystemExit):
            agent.main(["--json"])
        assert json.loads(capsys.readouterr().err) == {"error": "down"}
