"""Tests for yahoo_finance: parse_date, window args, session dates, crumb handshake,
fetch_quote_summary, summary_num/summary_text, build_params, meta_summary, extract_series,
fetch_history, and the stock_data adapter (parse_analyst_view, analyst_view,
parse_earnings_view, earnings_view)."""

import argparse
import datetime as dt

import pytest
import requests

import yahoo_finance as yf
from helpers import FakeResponse, FakeSession


class TestParseDate:
    def test_valid_returns_utc_midnight(self):
        result = yf.parse_date("2024-03-15")
        assert result == dt.datetime(2024, 3, 15, tzinfo=dt.timezone.utc)
        assert result.tzinfo is dt.timezone.utc

    @pytest.mark.parametrize("bad", ["2024-13-01", "2024-02-30", "15-03-2024", "foo", ""])
    def test_invalid_raises_valueerror(self, bad):
        with pytest.raises(ValueError, match="invalid date"):
            yf.parse_date(bad)


class TestAddWindowArgs:
    def _parser(self):
        parser = argparse.ArgumentParser()
        yf.add_window_args(parser, "6mo", "only the last N")
        return parser

    def test_defaults(self):
        args = self._parser().parse_args([])
        assert (args.range, args.last, args.start, args.end) == ("6mo", None, None, None)

    def test_start_end_and_last_parse(self):
        args = self._parser().parse_args(["--last", "5", "--start", "2024-01-01", "--end", "2024-02-01"])
        assert (args.last, args.start, args.end) == (5, "2024-01-01", "2024-02-01")

    @pytest.mark.parametrize("argv", [
        ["--range", "1mo", "--last", "5"],   # mutually exclusive
        ["--range", "7d"],                   # not a Yahoo range
        ["--last", "0"],                     # positive_int
    ])
    def test_rejects_exit_2(self, argv):
        with pytest.raises(SystemExit) as exc:
            self._parser().parse_args(argv)
        assert exc.value.code == 2


class TestSessionDatetime:
    def test_applies_gmtoffset_and_is_naive(self):
        # 2024-01-02 23:30 UTC is already 2024-01-03 at UTC+8.
        ts = int(dt.datetime(2024, 1, 2, 23, 30, tzinfo=dt.timezone.utc).timestamp())
        result = yf.session_datetime(ts, 8 * 3600)
        assert result == dt.datetime(2024, 1, 3, 7, 30)
        assert result.tzinfo is None

    def test_negative_offset_moves_date_back(self):
        ts = int(dt.datetime(2024, 1, 3, 2, 0, tzinfo=dt.timezone.utc).timestamp())
        assert yf.session_datetime(ts, -5 * 3600).date() == dt.date(2024, 1, 2)


class _RaisingFirstGetSession(FakeSession):
    """FakeSession whose first ``n`` GETs raise a connection error."""

    def __init__(self, n, **kwargs):
        super().__init__(**kwargs)
        self._fail = n

    def get(self, url, **kwargs):
        if self._fail:
            self._fail -= 1
            self.get_calls.append((url, kwargs))
            raise requests.ConnectionError("down")
        return super().get(url, **kwargs)


class TestFetchCrumb:
    def test_cookie_then_crumb(self):
        session = FakeSession(get_responses=[FakeResponse(text="ok"), FakeResponse(text=" crumb123\t")])
        assert yf.fetch_crumb(session) == "crumb123"
        assert [c[0] for c in session.get_calls] == [yf.COOKIE_URLS[0], yf.CRUMB_URL]
        assert all(c[1]["timeout"] == yf.REQUEST_TIMEOUT for c in session.get_calls)

    def test_falls_back_to_next_cookie_page(self):
        session = _RaisingFirstGetSession(
            1, get_responses=[FakeResponse(text="ok"), FakeResponse(text="crumb123")]
        )
        assert yf.fetch_crumb(session) == "crumb123"
        assert [c[0] for c in session.get_calls] == [*yf.COOKIE_URLS, yf.CRUMB_URL]

    def test_crumb_request_error_returns_none(self):
        session = _RaisingFirstGetSession(len(yf.COOKIE_URLS) + 1)
        assert yf.fetch_crumb(session) is None

    @pytest.mark.parametrize("crumb_response", [
        FakeResponse(text="<html>consent</html>"),
        FakeResponse(text="   "),
        FakeResponse(text="x" * 64),
        FakeResponse(text="crumb123", status_code=401),
    ])
    def test_unusable_crumb_returns_none(self, crumb_response):
        session = FakeSession(get_responses=[FakeResponse(text="ok"), crumb_response])
        assert yf.fetch_crumb(session) is None


class TestCrumbSession:
    def test_session_has_headers_and_crumb(self, monkeypatch):
        session = FakeSession(get_responses=[FakeResponse(text="ok"), FakeResponse(text="crumb123")])
        monkeypatch.setattr(yf.requests, "Session", lambda: session)
        assert yf.crumb_session() == (session, "crumb123")
        assert session.headers == yf.HEADERS


class TestFetchQuoteSummary:
    def test_requests_the_given_modules_with_crumb(self, monkeypatch):
        session = FakeSession(get_responses=[
            FakeResponse(text="cookie"),
            FakeResponse(text="crumb123"),
            FakeResponse(json_data={"quoteSummary": {"result": [{"price": {}}], "error": None}}),
        ])
        monkeypatch.setattr(yf.requests, "Session", lambda: session)
        assert yf.fetch_quote_summary("AAA", ["price", "calendarEvents"]) == {"price": {}}
        url, kwargs = session.get_calls[2]
        assert url == yf.QUOTE_SUMMARY_HOSTS[0].format(symbol="AAA")
        assert kwargs["params"] == {
            "modules": "price,calendarEvents", "formatted": "false", "crumb": "crumb123"}

    def test_empty_result_raises(self, monkeypatch):
        session = FakeSession(get_responses=[FakeResponse(text="cookie"), FakeResponse(text="")]
                              + [FakeResponse(json_data={"quoteSummary": {"result": []}})] * 2)
        monkeypatch.setattr(yf.requests, "Session", lambda: session)
        with pytest.raises(requests.RequestException, match="no fundamentals in response"):
            yf.fetch_quote_summary("AAA", ["price"])


class TestSummaryNumText:
    @pytest.mark.parametrize("node,expected", [
        ({"a": {"b": 3}}, 3.0),
        ({"a": {"b": {"raw": 1.5, "fmt": "1.50"}}}, 1.5),
        ({"a": {"b": True}}, None),
        ({"a": {"b": "7"}}, None),
        ({"a": None}, None),
    ])
    def test_num(self, node, expected):
        assert yf.summary_num(node, "a", "b") == expected

    @pytest.mark.parametrize("node,expected", [
        ({"a": {"b": "Tech"}}, "Tech"),
        ({"a": {"b": ""}}, None),
        ({"a": {"b": 3}}, None),
        ({"a": "flat"}, None),
    ])
    def test_text(self, node, expected):
        assert yf.summary_text(node, "a", "b") == expected


class TestBuildParams:
    def test_range_branch_is_default(self):
        params = yf.build_params(range_="6mo")
        assert params["range"] == "6mo"
        assert params["interval"] == "1d"
        assert params["includeAdjustedClose"] == "true"
        assert "period1" not in params and "period2" not in params

    def test_explicit_start_end(self):
        params = yf.build_params(start="2024-01-01", end="2024-01-31")
        start_ts = int(dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp())
        end_ts = int(dt.datetime(2024, 1, 31, tzinfo=dt.timezone.utc).timestamp())
        assert params["period1"] == start_ts
        assert params["period2"] == end_ts + yf.SECONDS_PER_DAY  # end padded a day
        assert "range" not in params

    def test_start_only_uses_now_as_end(self):
        before = dt.datetime.now(dt.timezone.utc).timestamp()
        params = yf.build_params(start="2020-01-01")
        after = dt.datetime.now(dt.timezone.utc).timestamp()
        assert params["period1"] == int(
            dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc).timestamp()
        )
        assert before + yf.SECONDS_PER_DAY - 2 <= params["period2"] <= after + yf.SECONDS_PER_DAY + 2

    def test_end_without_start_raises(self):
        with pytest.raises(ValueError, match="--end requires --start"):
            yf.build_params(end="2024-01-01")

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError, match="must not be before"):
            yf.build_params(start="2024-02-01", end="2024-01-01")

    def test_equal_start_end_is_one_day(self):
        params = yf.build_params(start="2024-01-01", end="2024-01-01")
        start_ts = int(dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp())
        assert params["period1"] == start_ts
        assert params["period2"] == start_ts + yf.SECONDS_PER_DAY

    def test_last_daily_lookback_window(self):
        params = yf.build_params(last=5)
        span_days = (params["period2"] - params["period1"]) / yf.SECONDS_PER_DAY
        # lookback = 5*2 + 10 = 20 days, plus the one-day pad on period2
        assert span_days == pytest.approx(21, abs=0.1)
        assert "range" not in params

    def test_last_widens_for_weekly_and_monthly(self):
        daily = yf.build_params(last=5, interval="1d")
        weekly = yf.build_params(last=5, interval="1wk")
        monthly = yf.build_params(last=5, interval="1mo")
        assert weekly["period1"] < daily["period1"]
        assert monthly["period1"] < weekly["period1"]

    def test_start_end_takes_priority_over_last_and_range(self):
        params = yf.build_params(range_="6mo", start="2024-01-01", end="2024-02-01", last=9)
        assert params["period1"] == int(
            dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp()
        )
        assert "range" not in params

    def test_last_takes_priority_over_range(self):
        params = yf.build_params(range_="6mo", last=3)
        assert "range" not in params
        assert "period1" in params


class TestMetaSummary:
    def test_full_meta(self):
        meta = {"symbol": "D05.SI", "fullExchangeName": "Singapore", "currency": "SGD"}
        assert yf.meta_summary(meta, "x") == ("D05.SI", "Singapore", "SGD")

    def test_exchange_name_fallback(self):
        assert yf.meta_summary({"symbol": "X", "exchangeName": "NMS"}) == ("X", "NMS", "")

    def test_missing_symbol_uses_fallback(self):
        assert yf.meta_summary({}, "AAPL") == ("AAPL", "?", "")

    def test_empty_meta_no_fallback(self):
        assert yf.meta_summary({}) == ("?", "?", "")

    def test_blank_values_fall_through(self):
        assert yf.meta_summary({"symbol": "", "currency": ""}, "AAPL") == ("AAPL", "?", "")


class TestExtractSeries:
    def test_wellformed(self, chart_result):
        meta, series = yf.extract_series(chart_result)
        assert meta["symbol"] == "AAA"
        assert series["gmtoffset"] == 0
        assert series["timestamp"] == [1704067200, 1704153600, 1704240000]
        assert series["open"] == [10.0, 11.0, 12.0]
        assert series["close"] == [10.2, 11.2, 12.2]
        assert series["volume"] == [1000, 2000, 3000]
        assert series["adjclose"] == [10.1, 11.1, 12.1]

    def test_empty_result(self):
        meta, series = yf.extract_series({})
        assert meta == {}
        assert series["timestamp"] == []
        assert series["open"] == []
        assert series["adjclose"] is None
        assert series["gmtoffset"] == 0

    def test_gmtoffset_none_coerced_to_zero(self):
        _, series = yf.extract_series({"meta": {"gmtoffset": None}})
        assert series["gmtoffset"] == 0

    def test_missing_adjclose_block(self, chart_result):
        del chart_result["indicators"]["adjclose"]
        _, series = yf.extract_series(chart_result)
        assert series["adjclose"] is None


class TestFetchHistory:
    def _patch_get(self, monkeypatch, response):
        monkeypatch.setattr(yf.requests, "get", lambda url, **kwargs: response)

    def test_happy_path_returns_first_result(self, monkeypatch, chart_result):
        payload = {"chart": {"result": [chart_result], "error": None}}
        self._patch_get(monkeypatch, FakeResponse(json_data=payload))
        assert yf.fetch_history("AAA", {}) is chart_result

    def test_calls_get_with_expected_url_headers_timeout_params(self, monkeypatch, chart_result):
        payload = {"chart": {"result": [chart_result], "error": None}}
        calls = {}

        def fake_get(url, **kwargs):
            calls["url"] = url
            calls.update(kwargs)
            return FakeResponse(json_data=payload)

        monkeypatch.setattr(yf.requests, "get", fake_get)
        params = {"range": "6mo"}
        yf.fetch_history("AAA", params)
        assert calls["url"] == yf.CHART_URL.format(symbol="AAA")
        assert calls["headers"] == yf.HEADERS
        assert calls["timeout"] == yf.REQUEST_TIMEOUT
        assert calls["params"] is params

    def test_chart_error_raises(self, monkeypatch):
        payload = {"chart": {"result": None, "error": {"description": "Not Found"}}}
        self._patch_get(monkeypatch, FakeResponse(json_data=payload))
        with pytest.raises(requests.RequestException, match="Not Found"):
            yf.fetch_history("BAD", {})

    def test_no_results_raises(self, monkeypatch):
        payload = {"chart": {"result": [], "error": None}}
        self._patch_get(monkeypatch, FakeResponse(json_data=payload))
        with pytest.raises(requests.RequestException, match="no data returned"):
            yf.fetch_history("AAA", {})

    def test_non_json_raises_http_error(self, monkeypatch):
        resp = FakeResponse(json_data=None, raise_for_status=requests.HTTPError("500"))
        self._patch_get(monkeypatch, resp)
        with pytest.raises(requests.HTTPError):
            yf.fetch_history("AAA", {})

    def test_non_json_without_http_error_reraises_valueerror(self, monkeypatch):
        self._patch_get(monkeypatch, FakeResponse(json_data=None))
        with pytest.raises(ValueError):
            yf.fetch_history("AAA", {})


# --------------------------------------------------------------------------- #
# stock_data adapter                                                           #
# --------------------------------------------------------------------------- #
DAY = 86400
NOW = 1_790_000_000  # 2026-09-21 14:13 UTC


def _trend(period, strong_buy, buy, hold, sell, strong_sell):
    return {"period": period, "strongBuy": strong_buy, "buy": buy, "hold": hold,
            "sell": sell, "strongSell": strong_sell}


def _grade(days_ago, firm, action, from_grade, to_grade, target_action="", target=0.0,
           prior=0.0):
    return {"epochGradeDate": int(NOW - days_ago * DAY), "firm": firm, "action": action,
            "fromGrade": from_grade, "toGrade": to_grade,
            "priceTargetAction": target_action, "currentPriceTarget": target,
            "priorPriceTarget": prior}


def _history():
    """``upgradeDowngradeHistory`` out of date order, one entry outside 90 days."""
    return {"history": [
        _grade(10, "Beta Bank", "down", "Buy", "Hold", "Lowers", 120.0, 140.0),
        _grade(2, "Alpha Capital", "up", "Hold", "Buy", "Raises", 150.0, 130.0),
        _grade(200, "Old Firm", "init", "", "Buy", "Announces", 90.0, 0.0),
        _grade(30, "Gamma Research", "reit", "Neutral", "Neutral", "", 0.0, 0.0),
        _grade(45, "Delta Partners", "main", "Outperform", "Outperform", "Maintains",
               115.0, 115.0),
    ]}


def _analyst_modules(price=100.0):
    """quoteSummary ``modules`` with every field parse_analyst_view() reads."""
    return {
        "price": {"longName": "Triple A Inc.", "currency": "USD", "exchangeName": "TST",
                  "regularMarketPrice": {"raw": price}},
        "financialData": {
            "currentPrice": {"raw": price},
            "targetLowPrice": {"raw": 80.0}, "targetMedianPrice": {"raw": 110.0},
            "targetMeanPrice": {"raw": 105.0}, "targetHighPrice": {"raw": 150.0},
            "numberOfAnalystOpinions": {"raw": 20},
            "recommendationKey": "buy", "recommendationMean": {"raw": 2.2},
        },
        "recommendationTrend": {"trend": [
            # Out of order on purpose: the parser sorts newest first.
            _trend("-1m", 5, 9, 5, 1, 0),
            _trend("0m", 6, 10, 4, 1, 1),
        ]},
        "upgradeDowngradeHistory": _history(),
    }


class TestParseAnalystView:
    def test_profile_price_targets_consensus(self):
        view = yf.parse_analyst_view(_analyst_modules(), 90, now=NOW)
        assert (view["source"], view["notes"]) == ("Yahoo Finance", [])
        assert (view["name"], view["exchange"], view["currency"]) == ("Triple A Inc.", "TST", "USD")
        assert view["price"] == 100.0
        assert view["targets"] == {"low": 80.0, "median": 110.0, "mean": 105.0, "high": 150.0}
        assert view["analysts"] == 20
        assert view["recommendation"] == {"key": "buy", "mean": 2.2}

    def test_short_name_and_missing_currency(self):
        view = yf.parse_analyst_view({"price": {"shortName": "AAA"}}, 90, now=NOW)
        assert (view["name"], view["exchange"], view["currency"]) == ("AAA", None, "")

    def test_price_falls_back_to_regular_market_price(self):
        modules = _analyst_modules(price=42.0)
        del modules["financialData"]["currentPrice"]
        assert yf.parse_analyst_view(modules, 90, now=NOW)["price"] == 42.0

    def test_no_price(self):
        modules = _analyst_modules()
        del modules["financialData"]["currentPrice"]
        del modules["price"]["regularMarketPrice"]
        assert yf.parse_analyst_view(modules, 90, now=NOW)["price"] is None

    def test_recommendation_key_none_is_dropped(self):
        modules = _analyst_modules()
        modules["financialData"]["recommendationKey"] = "none"
        assert yf.parse_analyst_view(modules, 90, now=NOW)["recommendation"]["key"] is None

    def test_trend_sorted_newest_first_without_totals(self):
        rows = yf.parse_analyst_view(_analyst_modules(), 90, now=NOW)["trend"]
        assert [r["period"] for r in rows] == ["0m", "-1m"]
        assert rows[0] == {"period": "0m", "strong_buy": 6, "buy": 10, "hold": 4,
                           "sell": 1, "strong_sell": 1}

    def test_empty_trend_rows_dropped(self):
        modules = {"recommendationTrend": {"trend": [{"period": "0m"}]}}
        assert yf.parse_analyst_view(modules, 90, now=NOW)["trend"] == []

    def test_no_coverage_is_all_empty(self):
        view = yf.parse_analyst_view({"price": {"currency": "USD"}}, 90, now=NOW)
        assert set(view["targets"].values()) == {None}
        assert (view["analysts"], view["trend"], view["actions"]) == (None, [], [])


class TestAnalystActions:
    def _actions(self, days, history=None):
        modules = {"upgradeDowngradeHistory": history or _history()}
        return yf.parse_analyst_view(modules, days, now=NOW)["actions"]

    def test_window_and_newest_first(self):
        assert [r["firm"] for r in self._actions(90)] == [
            "Alpha Capital", "Beta Bank", "Gamma Research", "Delta Partners"]

    def test_fields_and_mapping(self):
        rows = self._actions(90)
        assert rows[0] == {
            "date": "2026-09-19", "firm": "Alpha Capital", "action": "upgrade",
            "from_grade": "Hold", "to_grade": "Buy", "target_action": "raised",
            "target": 150.0, "prior_target": 130.0,
        }
        assert (rows[1]["action"], rows[1]["target_action"]) == ("downgrade", "lowered")
        assert (rows[3]["action"], rows[3]["target_action"]) == ("maintain", "maintained")

    def test_zero_targets_and_blank_text_become_none(self):
        gamma = self._actions(90)[2]
        assert gamma["action"] == "reiterate"
        assert (gamma["target_action"], gamma["target"], gamma["prior_target"]) == (None, None, None)
        old = self._actions(365)[-1]
        assert (old["action"], old["from_grade"], old["prior_target"]) == ("initiate", None, None)

    def test_days_narrows_window(self):
        assert [r["firm"] for r in self._actions(7)] == ["Alpha Capital"]

    def test_unknown_codes_pass_through_and_undated_skipped(self):
        history = {"history": [
            _grade(1, "X", "xyz", "A", "B", "Rethinks", 1.0),
            {"firm": "No Date", "action": "up"},
        ]}
        rows = self._actions(90, history)
        assert [(r["action"], r["target_action"]) for r in rows] == [("xyz", "rethinks")]

    def test_missing_module(self):
        assert yf.parse_analyst_view({"price": {}}, 90, now=NOW)["actions"] == []


class TestAnalystView:
    def test_fetches_analyst_modules(self, monkeypatch):
        seen = []
        monkeypatch.setattr(yf, "fetch_quote_summary",
                            lambda s, m: seen.append((s, m)) or _analyst_modules())
        view = yf.analyst_view("AAA", 90)
        assert seen == [("AAA", yf.ANALYST_MODULES)]
        assert view["targets"]["high"] == 150.0

    def test_fetch_error_propagates(self, monkeypatch):
        def boom(symbol, modules):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(yf, "fetch_quote_summary", boom)
        with pytest.raises(requests.RequestException, match="Quote not found"):
            yf.analyst_view("ZZZ", 90)


def _ts(text):
    """'YYYY-MM-DD[ HH:MM]' (UTC) -> epoch seconds."""
    fmt = "%Y-%m-%d %H:%M" if " " in text else "%Y-%m-%d"
    return int(dt.datetime.strptime(text, fmt).replace(tzinfo=dt.timezone.utc).timestamp())


def _history_entry(quarter, estimate, actual, surprise):
    return {"quarter": {"raw": _ts(quarter), "fmt": quarter},
            "epsEstimate": {"raw": estimate}, "epsActual": {"raw": actual},
            "surprisePercent": {"raw": surprise}, "currency": "USD"}


def _earnings_modules():
    """quoteSummary ``modules`` with every field parse_earnings_view() reads."""
    return {
        "price": {"longName": "Triple A Inc.", "currency": "USD", "exchangeName": "TST"},
        "financialData": {"financialCurrency": "USD"},
        "defaultKeyStatistics": {"lastDividendValue": {"raw": 0.27},
                                 "lastDividendDate": {"raw": _ts("2026-08-10")}},
        "calendarEvents": {
            "earnings": {
                "earningsDate": [_ts("2026-11-02 20:00")],
                "isEarningsDateEstimate": False,
                "earningsLow": 1.93, "earningsAverage": 1.98, "earningsHigh": 2.07,
                "revenueLow": 112e9, "revenueAverage": 113.6e9, "revenueHigh": 117e9,
            },
            "exDividendDate": _ts("2026-08-10"),
            "dividendDate": _ts("2026-10-20"),
        },
        "earningsHistory": {"history": [
            # Out of order on purpose: the parser sorts oldest first.
            _history_entry("2026-06-30", 1.89, 2.02, 0.0674),
            _history_entry("2026-03-31", 1.94, 2.01, 0.0346),
        ]},
        "earnings": {"earningsChart": {"quarterly": [
            {"fiscalQuarter": "2Q2026", "periodEndDate": _ts("2026-03-31"),
             "reportedDate": _ts("2026-04-30 20:30")},
            {"fiscalQuarter": "3Q2026", "periodEndDate": _ts("2026-06-30"),
             "reportedDate": _ts("2026-07-30 20:30")},
        ]}},
    }


class TestParseEarningsView:
    def test_profile_and_reporting_currency(self):
        view = yf.parse_earnings_view(_earnings_modules())
        assert (view["source"], view["notes"]) == ("Yahoo Finance", [])
        assert (view["name"], view["exchange"], view["currency"]) == ("Triple A Inc.", "TST", "USD")
        assert view["reporting_currency"] == "USD"

    def test_reporting_currency_falls_back_to_history_then_none(self):
        modules = _earnings_modules()
        del modules["financialData"]
        modules["earningsHistory"]["history"][0]["currency"] = "EUR"
        assert yf.parse_earnings_view(modules)["reporting_currency"] == "EUR"
        modules["earningsHistory"] = {}
        assert yf.parse_earnings_view(modules)["reporting_currency"] is None

    def test_no_earnings_data(self):
        view = yf.parse_earnings_view({"price": {"currency": "USD"}})
        assert (view["next_earnings"], view["dividend"], view["earnings_history"]) == (None, None, [])


class TestNextEarnings:
    def test_confirmed_date(self):
        nxt = yf.parse_earnings_view(_earnings_modules())["next_earnings"]
        assert nxt["date"] == nxt["date_end"] == "2026-11-02"
        assert nxt["datetime_utc"] == "2026-11-02T20:00Z"
        assert nxt["is_estimate"] is False
        assert "status" not in nxt  # the script adds it against today
        assert nxt["eps_estimate"] == {"low": 1.93, "average": 1.98, "high": 2.07}
        assert nxt["revenue_estimate"]["average"] == 113.6e9

    def test_two_timestamps_are_an_estimated_window(self):
        modules = _earnings_modules()
        modules["calendarEvents"]["earnings"]["earningsDate"] = [
            _ts("2026-11-09"), _ts("2026-11-02")]
        nxt = yf.parse_earnings_view(modules)["next_earnings"]
        assert (nxt["date"], nxt["date_end"]) == ("2026-11-02", "2026-11-09")
        assert nxt["is_estimate"] is True

    def test_no_estimates_gives_none(self):
        modules = _earnings_modules()
        modules["calendarEvents"]["earnings"] = {"earningsDate": [_ts("2026-11-02")]}
        nxt = yf.parse_earnings_view(modules)["next_earnings"]
        assert nxt["eps_estimate"] is None and nxt["revenue_estimate"] is None

    @pytest.mark.parametrize("calendar", [{}, {"earnings": {}}, {"earnings": {"earningsDate": []}}])
    def test_no_date_returns_none(self, calendar):
        assert yf.parse_earnings_view({"calendarEvents": calendar})["next_earnings"] is None


class TestDividend:
    def test_dates_and_amount(self):
        div = yf.parse_earnings_view(_earnings_modules())["dividend"]
        assert div == {
            "ex_dividend_date": "2026-08-10", "payment_date": "2026-10-20",
            "last_amount": 0.27, "last_amount_date": "2026-08-10", "amount_currency": "USD",
        }

    @pytest.mark.parametrize("currency", ["GBp", "GBX", "ILA", "ZAc"])
    def test_minor_unit_listing_has_no_amount_currency(self, currency):
        modules = _earnings_modules()
        modules["price"]["currency"] = currency
        assert yf.parse_earnings_view(modules)["dividend"]["amount_currency"] is None

    def test_no_dividend_returns_none(self):
        assert yf.parse_earnings_view({"calendarEvents": {"earnings": {}}})["dividend"] is None


class TestEarningsHistory:
    def test_sorted_and_matched_to_chart(self):
        rows = yf.parse_earnings_view(_earnings_modules())["earnings_history"]
        assert [r["quarter_end"] for r in rows] == ["2026-03-31", "2026-06-30"]
        assert rows[1] == {
            "quarter_end": "2026-06-30", "fiscal_quarter": "3Q2026",
            "reported_date": "2026-07-30", "eps_estimate": 1.89, "eps_actual": 2.02,
            "surprise_pct": 0.0674, "currency": "USD",
        }

    def test_unmatched_quarter_has_no_report_date(self):
        modules = _earnings_modules()
        modules["earnings"] = {}
        row = yf.parse_earnings_view(modules)["earnings_history"][0]
        assert row["fiscal_quarter"] is None and row["reported_date"] is None

    def test_rows_without_eps_dropped(self):
        modules = _earnings_modules()
        modules["earningsHistory"]["history"].append({"quarter": {"raw": _ts("2026-09-30")}})
        assert len(yf.parse_earnings_view(modules)["earnings_history"]) == 2


class TestEarningsView:
    def test_fetches_earnings_modules(self, monkeypatch):
        seen = []
        monkeypatch.setattr(yf, "fetch_quote_summary",
                            lambda s, m: seen.append((s, m)) or _earnings_modules())
        view = yf.earnings_view("AAA")
        assert seen == [("AAA", yf.EARNINGS_MODULES)]
        assert view["next_earnings"]["date"] == "2026-11-02"

    def test_fetch_error_propagates(self, monkeypatch):
        def boom(symbol, modules):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(yf, "fetch_quote_summary", boom)
        with pytest.raises(requests.RequestException, match="Quote not found"):
            yf.earnings_view("ZZZ")
