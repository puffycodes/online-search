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

EARNINGS_VIEW_KEYS = {"source", "notes", "name", "exchange", "currency",
                      "reporting_currency", "next_earnings", "dividend", "earnings_history"}
NEXT_EARNINGS_KEYS = {"date", "date_end", "datetime_utc", "is_estimate", "eps_estimate",
                      "revenue_estimate"}
ESTIMATE_KEYS = {"low", "average", "high"}
DIVIDEND_KEYS = {"ex_dividend_date", "payment_date", "last_amount", "last_amount_date",
                 "amount_currency"}
QUARTER_KEYS = {"quarter_end", "fiscal_quarter", "reported_date", "eps_estimate",
                "eps_actual", "surprise_pct", "currency"}

HOLDERS_VIEW_KEYS = {"source", "notes", "name", "exchange", "currency", "us_listing",
                     "transaction_currency", "ownership", "transactions", "top_funds",
                     "top_institutions"}
OWNERSHIP_KEYS = {"insiders_pct", "institutions_pct", "institutions_float_pct",
                  "institutions_count"}
TRANSACTION_KEYS = {"date", "name", "relation", "kind", "text", "shares", "value",
                    "price_low", "price_high", "ownership"}
TRANSACTION_KINDS = {"sale", "purchase", "option_exercise", "award", "gift", "buyback",
                     "holder_disclosure", "other", "unspecified"}
HOLDER_KEYS = {"name", "pct_held", "shares", "value", "pct_change", "report_date"}

FUNDAMENTALS_VIEW_KEYS = {
    "source", "notes", "name", "exchange", "currency", "sector", "industry", "price",
    "market_cap", "shares_outstanding", "free_cash_flow", "operating_cash_flow", "ebitda",
    "revenue", "net_income", "total_debt", "total_cash", "eps_ttm", "eps_forward",
    "book_value_per_share", "beta", "trailing_pe", "forward_pe", "price_to_sales",
    "price_to_book", "enterprise_value", "ev_to_ebitda", "gross_margin", "operating_margin",
    "net_margin", "return_on_equity", "return_on_assets", "revenue_growth", "earnings_growth",
    "debt_to_equity", "current_ratio", "quick_ratio", "dividend_per_share", "payout_ratio",
    "analyst_growth_1y", "analyst_growth_5y",
}

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
YAHOO_EARNINGS_MODULES = {
    "price": {"longName": "Triple A Inc.", "currency": "USD", "exchangeName": "TST"},
    "financialData": {"financialCurrency": "USD"},
    "defaultKeyStatistics": {"lastDividendValue": {"raw": 0.27},
                             "lastDividendDate": {"raw": NOW - 40 * 86400}},
    "calendarEvents": {
        "earnings": {"earningsDate": [NOW + 30 * 86400], "earningsAverage": 1.98,
                     "revenueAverage": 113.6e9},
        "exDividendDate": NOW - 40 * 86400, "dividendDate": NOW + 10 * 86400,
    },
    "earningsHistory": {"history": [
        {"quarter": {"raw": NOW - 80 * 86400}, "epsEstimate": {"raw": 1.89},
         "epsActual": {"raw": 2.02}, "surprisePercent": {"raw": 0.0674}, "currency": "USD"}]},
}
_YAHOO_HOLDER = {"organization": "Index Fund", "pctHeld": {"raw": 0.03},
                 "position": {"raw": 3_000_000}, "value": {"raw": 30_000_000},
                 "pctChange": {"raw": 0.01}, "reportDate": {"raw": NOW - 60 * 86400}}
YAHOO_HOLDERS_MODULES = {
    "price": {"longName": "Triple A Inc.", "currency": "USD", "exchangeName": "TST"},
    "majorHoldersBreakdown": {"insidersPercentHeld": 0.02, "institutionsPercentHeld": 0.6,
                              "institutionsFloatPercentHeld": 0.61, "institutionsCount": 900},
    "insiderTransactions": {"transactions": [
        {"startDate": {"raw": NOW - 5 * 86400}, "filerName": "ROE RICHARD",
         "filerRelation": "Director", "transactionText": "Sale at price 11.50 per share.",
         "shares": {"raw": 1000}, "value": {"raw": 11500}, "ownership": "D"}]},
    "fundOwnership": {"ownershipList": [_YAHOO_HOLDER]},
    "institutionOwnership": {"ownershipList": [_YAHOO_HOLDER]},
}
YAHOO_FUNDAMENTALS_MODULES = {
    "price": {"longName": "Triple A Inc.", "currency": "USD", "exchangeName": "TST",
              "marketCap": {"raw": 100e9}},
    "financialData": {"currentPrice": {"raw": 100.0}, "freeCashflow": {"raw": 5e9},
                      "debtToEquity": {"raw": 150.0}, "grossMargins": {"raw": 0.45}},
    "defaultKeyStatistics": {"sharesOutstanding": {"raw": 1e9}, "beta": {"raw": 1.2}},
    "summaryDetail": {"trailingPE": {"raw": 20.0}, "dividendYield": {"raw": 0.02}},
    "summaryProfile": {"sector": "Technology", "industry": "Consumer Electronics"},
    "earningsTrend": {"trend": [{"period": "+5y", "growth": {"raw": 0.10}}]},
}


class TestRouting:
    def test_analyst_view_is_served_by_yahoo(self):
        assert stock_data.PROVIDERS["analyst_view"] is yf.analyst_view

    def test_earnings_view_is_served_by_yahoo(self):
        assert stock_data.PROVIDERS["earnings_view"] is yf.earnings_view

    def test_earnings_view_delegates_to_its_provider(self, monkeypatch):
        seen = []
        monkeypatch.setitem(stock_data.PROVIDERS, "earnings_view",
                            lambda s: seen.append(s) or {"ok": True})
        assert stock_data.earnings_view("AAA") == {"ok": True}
        assert seen == ["AAA"]

    def test_holders_view_is_served_by_yahoo(self):
        assert stock_data.PROVIDERS["holders_view"] is yf.holders_view

    def test_holders_view_delegates_to_its_provider(self, monkeypatch):
        seen = []
        monkeypatch.setitem(stock_data.PROVIDERS, "holders_view",
                            lambda s, d: seen.append((s, d)) or {"ok": True})
        assert stock_data.holders_view("AAA", 30) == {"ok": True}
        assert seen == [("AAA", 30)]

    def test_fundamentals_view_is_served_by_yahoo(self):
        assert stock_data.PROVIDERS["fundamentals_view"] is yf.fundamentals_view

    def test_fundamentals_view_delegates_to_its_provider(self, monkeypatch):
        seen = []
        monkeypatch.setitem(stock_data.PROVIDERS, "fundamentals_view",
                            lambda s: seen.append(s) or {"ok": True})
        assert stock_data.fundamentals_view("AAA") == {"ok": True}
        assert seen == ["AAA"]

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


def _iso(value):
    return isinstance(value, str) and len(value) == 10 and value[4] == value[7] == "-"


@pytest.mark.parametrize("view", [
    pytest.param(yf.parse_earnings_view(YAHOO_EARNINGS_MODULES), id="yahoo"),
])
class TestEarningsViewContract:
    def test_top_level_keys(self, view):
        assert set(view) == EARNINGS_VIEW_KEYS
        assert isinstance(view["source"], str) and view["source"]
        assert isinstance(view["notes"], list)

    def test_part_keys(self, view):
        nxt = view["next_earnings"]
        assert set(nxt) == NEXT_EARNINGS_KEYS
        assert set(nxt["eps_estimate"]) == ESTIMATE_KEYS
        assert set(nxt["revenue_estimate"]) == ESTIMATE_KEYS
        assert set(view["dividend"]) == DIVIDEND_KEYS
        assert view["earnings_history"]
        assert all(set(row) == QUARTER_KEYS for row in view["earnings_history"])

    def test_values_are_plain(self, view):
        nxt = view["next_earnings"]
        assert _iso(nxt["date"]) and _iso(nxt["date_end"])
        assert isinstance(nxt["is_estimate"], bool)
        assert all(_iso(view["dividend"][k]) for k in ("ex_dividend_date", "payment_date",
                                                       "last_amount_date"))
        for row in view["earnings_history"]:
            assert _iso(row["quarter_end"])
            assert all(row[k] is None or isinstance(row[k], (int, float))
                       for k in ("eps_estimate", "eps_actual", "surprise_pct"))


@pytest.mark.parametrize("view", [
    pytest.param(yf.parse_holders_view("AAA", YAHOO_HOLDERS_MODULES, 180, now=NOW), id="yahoo"),
])
class TestHoldersViewContract:
    def test_top_level_keys(self, view):
        assert set(view) == HOLDERS_VIEW_KEYS
        assert isinstance(view["source"], str) and view["source"]
        assert isinstance(view["notes"], list)
        assert isinstance(view["us_listing"], bool)

    def test_part_keys(self, view):
        assert set(view["ownership"]) == OWNERSHIP_KEYS
        assert view["transactions"]
        assert all(set(t) == TRANSACTION_KEYS for t in view["transactions"])
        assert view["top_funds"] and view["top_institutions"]
        assert all(set(h) == HOLDER_KEYS for h in view["top_funds"] + view["top_institutions"])

    def test_values_are_plain(self, view):
        assert all(v is None or isinstance(v, (int, float)) for v in view["ownership"].values())
        assert isinstance(view["ownership"]["institutions_count"], int)
        for t in view["transactions"]:
            assert _iso(t["date"]) and t["kind"] in TRANSACTION_KINDS
            assert t["shares"] is None or isinstance(t["shares"], int)
        for h in view["top_funds"]:
            assert _iso(h["report_date"]) and isinstance(h["shares"], int)


@pytest.mark.parametrize("view", [
    pytest.param(yf.parse_fundamentals_view(YAHOO_FUNDAMENTALS_MODULES), id="yahoo"),
])
class TestFundamentalsViewContract:
    def test_keys(self, view):
        assert set(view) == FUNDAMENTALS_VIEW_KEYS
        assert isinstance(view["source"], str) and view["source"]
        assert isinstance(view["notes"], list)

    def test_values_are_plain(self, view):
        text = {"source", "notes", "name", "exchange", "currency", "sector", "industry"}
        assert all(v is None or isinstance(v, (int, float))
                   for k, v in view.items() if k not in text)

    def test_ratios_are_fractions_not_percents(self, view):
        assert view["debt_to_equity"] == 1.5     # not 150
        assert view["gross_margin"] == 0.45      # not 45
        assert view["analyst_growth_5y"] == 0.10
        assert view["dividend_per_share"] == pytest.approx(2.0)  # per share, not a yield
