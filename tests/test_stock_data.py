"""Tests for stock_data: routing to the adapters, and the neutral shape every
adapter must return (a contract test, so a new provider can be checked
against the same keys)."""

import pytest

import stock_data
import yahoo_finance as yf

# The neutral analyst_view shape: top-level keys, then the keys inside each part.
ANALYST_VIEW_KEYS = {"source", "notes", "name", "exchange", "currency", "price",
                     "analysts", "targets", "recommendation", "trend", "actions"}
TARGET_KEYS = {"low", "median", "mean", "high"}
RECOMMENDATION_KEYS = {"key", "mean"}
TREND_KEYS = {"period", "strong_buy", "buy", "hold", "sell", "strong_sell"}
ACTION_KEYS = {"date", "firm", "action", "from_grade", "to_grade", "target_action",
               "target", "prior_target"}

NOW = 1_790_000_000  # 2026-09-21 14:13 UTC

# Raw data per adapter, filled in enough to produce a trend row and an action.
YAHOO_ANALYST_MODULES = {
    "price": {"longName": "Triple A Inc.", "currency": "USD", "exchangeName": "TST"},
    "financialData": {"currentPrice": {"raw": 100.0}, "targetHighPrice": {"raw": 150.0},
                      "recommendationKey": "buy"},
    "recommendationTrend": {"trend": [{"period": "0m", "strongBuy": 1, "buy": 2}]},
    "upgradeDowngradeHistory": {"history": [
        {"epochGradeDate": NOW - 86400, "firm": "Alpha", "action": "up",
         "fromGrade": "Hold", "toGrade": "Buy", "priceTargetAction": "Raises",
         "currentPriceTarget": 150.0, "priorPriceTarget": 130.0}]},
}


class TestRouting:
    def test_analyst_view_is_served_by_yahoo(self):
        assert stock_data.PROVIDERS["analyst_view"] is yf.analyst_view

    def test_analyst_view_delegates_to_its_provider(self, monkeypatch):
        seen = []
        monkeypatch.setitem(stock_data.PROVIDERS, "analyst_view",
                            lambda s, d: seen.append((s, d)) or {"ok": True})
        assert stock_data.analyst_view("AAA", 30) == {"ok": True}
        assert seen == [("AAA", 30)]

    def test_errors_propagate(self, monkeypatch):
        def boom(symbol, days):
            raise ValueError("bad answer")

        monkeypatch.setitem(stock_data.PROVIDERS, "analyst_view", boom)
        with pytest.raises(ValueError, match="bad answer"):
            stock_data.analyst_view("AAA", 30)


@pytest.mark.parametrize("view", [
    pytest.param(yf.parse_analyst_view(YAHOO_ANALYST_MODULES, 90, now=NOW), id="yahoo"),
])
class TestAnalystViewContract:
    def test_top_level_keys(self, view):
        assert set(view) == ANALYST_VIEW_KEYS
        assert isinstance(view["source"], str) and view["source"]
        assert isinstance(view["notes"], list)

    def test_part_keys(self, view):
        assert set(view["targets"]) == TARGET_KEYS
        assert set(view["recommendation"]) == RECOMMENDATION_KEYS
        assert view["trend"] and all(set(row) == TREND_KEYS for row in view["trend"])
        assert view["actions"] and all(set(a) == ACTION_KEYS for a in view["actions"])

    def test_values_are_plain(self, view):
        numbers = [view["price"], *view["targets"].values(), view["recommendation"]["mean"]]
        assert all(v is None or isinstance(v, (int, float)) for v in numbers)
        for row in view["trend"]:
            assert all(isinstance(row[k], int) for k in TREND_KEYS - {"period"})
        for action in view["actions"]:
            assert len(action["date"]) == 10 and action["date"][4] == "-"  # ISO date
