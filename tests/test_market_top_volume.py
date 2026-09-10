"""Tests for market_top_volume: config tables, quote formatting, get_movers, fetch_region_quotes, main()."""

import json

import pytest
import requests

import market_top_volume as mtv
from helpers import FakeResponse, FakeSession


class TestConfigTables:
    def test_metrics_have_required_keys(self):
        for name, spec in mtv.METRICS.items():
            assert {"scr_id", "sort_field", "sort_type", "key", "reverse"} <= set(spec), name

    def test_markets_have_required_keys(self):
        for name, cfg in mtv.MARKETS.items():
            assert {"region", "exchanges", "predefined"} <= set(cfg), name
            assert isinstance(cfg["predefined"], bool)

    def test_metric_labels_cover_metrics(self):
        assert set(mtv.METRIC_LABELS) == set(mtv.METRICS)


class TestQuoteToDict:
    def test_defaults_for_empty_quote(self):
        assert mtv.quote_to_dict(1, {}) == {
            "rank": 1, "symbol": "?", "name": "(unknown)", "exchange": "?",
            "volume": 0, "price": 0, "change_percent": 0, "currency": "",
        }

    def test_maps_fields(self):
        q = {"symbol": "AAA", "shortName": "Alpha", "fullExchangeName": "NYSE",
             "regularMarketVolume": 123, "regularMarketPrice": 10.5,
             "regularMarketChangePercent": 1.25, "currency": "USD"}
        row = mtv.quote_to_dict(3, q)
        assert (row["rank"], row["symbol"], row["name"], row["exchange"], row["volume"]) == (
            3, "AAA", "Alpha", "NYSE", 123,
        )


class TestFormatQuote:
    ROW = {"rank": 1, "symbol": "A", "name": "Alpha", "exchange": "NYSE",
           "volume": 100, "price": 5, "change_percent": 1.0, "currency": "USD"}

    def test_volume_metric_leads_with_volume(self):
        stats_line = mtv.format_quote(self.ROW, "volume").splitlines()[1]
        assert stats_line.index("Volume") < stats_line.index("Change")

    def test_mover_metric_leads_with_change(self):
        stats_line = mtv.format_quote(self.ROW, "gainers").splitlines()[1]
        assert stats_line.index("Change") < stats_line.index("Volume")


class TestGetMovers:
    @pytest.fixture(autouse=True)
    def _no_session(self, monkeypatch):
        monkeypatch.setattr(mtv, "_session", lambda: object())

    def test_predefined_sorted_and_limited(self, monkeypatch):
        quotes = [
            {"symbol": "A", "regularMarketVolume": 100, "regularMarketChangePercent": 1},
            {"symbol": "B", "regularMarketVolume": 300, "regularMarketChangePercent": 2},
            {"symbol": "C", "regularMarketVolume": 200, "regularMarketChangePercent": 3},
        ]
        monkeypatch.setattr(mtv, "fetch_predefined_quotes", lambda s, scr: list(quotes))
        out = mtv.get_movers("us", "volume", 2)
        assert [q["symbol"] for q in out] == ["B", "C"]

    def test_exchange_filter_applied(self, monkeypatch):
        quotes = [
            {"symbol": "A", "exchange": "NYQ", "regularMarketVolume": 100},
            {"symbol": "B", "exchange": "NMS", "regularMarketVolume": 300},
        ]
        monkeypatch.setattr(mtv, "fetch_predefined_quotes", lambda s, scr: list(quotes))
        assert [q["symbol"] for q in mtv.get_movers("nyse", "volume", 10)] == ["A"]

    def test_mover_volume_floor_filters(self, monkeypatch):
        quotes = [
            {"symbol": "A", "exchange": "NYQ", "regularMarketVolume": 10,
             "regularMarketChangePercent": 9},
            {"symbol": "B", "exchange": "NYQ", "regularMarketVolume": 1_000_000,
             "regularMarketChangePercent": 4},
        ]
        monkeypatch.setattr(mtv, "fetch_predefined_quotes", lambda s, scr: list(quotes))
        assert [q["symbol"] for q in mtv.get_movers("nyse", "gainers", 10)] == ["B"]

    def test_region_screener_used_for_non_us(self, monkeypatch):
        seen = {}

        def fake_region(session, region, sort_field, sort_type, min_volume=None):
            seen.update(region=region, sort_type=sort_type, min_volume=min_volume)
            return [{"symbol": "X", "exchange": "LSE", "regularMarketVolume": 5_000_000,
                     "regularMarketChangePercent": -3}]

        monkeypatch.setattr(mtv, "fetch_region_quotes", fake_region)
        mtv.get_movers("uk", "losers", 5)
        assert seen["region"] == "gb"
        assert seen["sort_type"] == "ASC"
        assert seen["min_volume"] == mtv.MIN_MOVER_VOLUME

    def test_region_screener_volume_metric_no_min(self, monkeypatch):
        seen = {}

        def fake_region(session, region, sort_field, sort_type, min_volume=None):
            seen["min_volume"] = min_volume
            return []

        monkeypatch.setattr(mtv, "fetch_region_quotes", fake_region)
        mtv.get_movers("uk", "volume", 5)
        assert seen["min_volume"] is None


class TestFetchRegionQuotes:
    def test_html_crumb_raises(self):
        session = FakeSession(get_responses=[
            FakeResponse(json_data={}),                # cookie
            FakeResponse(text="<html>nope</html>"),    # crumb
        ])
        with pytest.raises(requests.RequestException, match="crumb"):
            mtv.fetch_region_quotes(session, "gb", "dayvolume", "DESC")

    def test_empty_crumb_raises(self):
        session = FakeSession(get_responses=[
            FakeResponse(json_data={}),
            FakeResponse(text="   "),
        ])
        with pytest.raises(requests.RequestException, match="crumb"):
            mtv.fetch_region_quotes(session, "gb", "dayvolume", "DESC")

    def test_finance_error_raises(self):
        session = FakeSession(
            get_responses=[FakeResponse(json_data={}), FakeResponse(text="crumb123")],
            post_responses=[FakeResponse(json_data={"finance": {"error": "bad request"}})],
        )
        with pytest.raises(requests.RequestException, match="bad request"):
            mtv.fetch_region_quotes(session, "gb", "dayvolume", "DESC")

    def test_returns_quotes_and_sends_min_volume_operand(self):
        payload = {"finance": {"result": [{"quotes": [{"symbol": "X"}]}]}}
        session = FakeSession(
            get_responses=[FakeResponse(json_data={}), FakeResponse(text="crumb123")],
            post_responses=[FakeResponse(json_data=payload)],
        )
        out = mtv.fetch_region_quotes(session, "gb", "dayvolume", "DESC", min_volume=50_000)
        assert out == [{"symbol": "X"}]
        posted_body = session.post_calls[0][1]["json"]
        operand_fields = [o["operands"][0] for o in posted_body["query"]["operands"]]
        assert "dayvolume" in operand_fields
        assert session.post_calls[0][1]["params"] == {"crumb": "crumb123"}


class TestMain:
    def test_limit_below_one_is_clamped(self, monkeypatch, capsys):
        seen = {}

        def fake(market, metric, limit):
            seen["limit"] = limit
            return []

        monkeypatch.setattr(mtv, "get_movers", fake)
        mtv.main(["--limit", "0", "--json"])
        assert seen["limit"] == 1
        assert json.loads(capsys.readouterr().out) == []

    def test_error_exits_json(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise requests.RequestException("screener down")

        monkeypatch.setattr(mtv, "get_movers", boom)
        with pytest.raises(SystemExit):
            mtv.main(["--json"])
        assert "screener down" in json.loads(capsys.readouterr().err)["error"]
