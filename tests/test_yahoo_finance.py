"""Tests for yahoo_finance: parse_date, window args, session dates, crumb handshake, build_params,
meta_summary, extract_series, fetch_history."""

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

    def test_end_not_after_start_raises(self):
        with pytest.raises(ValueError, match="must be after"):
            yf.build_params(start="2024-02-01", end="2024-01-01")

    def test_equal_start_end_raises(self):
        with pytest.raises(ValueError, match="must be after"):
            yf.build_params(start="2024-01-01", end="2024-01-01")

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
