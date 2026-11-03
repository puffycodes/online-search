"""Tests for price_source: routing, window translation, bar aggregation, and
daily_history's neutral shape, provider dispatch and errors."""

import datetime as dt

import pytest
import requests

import alphavantage_price_history as avph
import eodhd_price_history as eodph
import price_source as ps
import yahoo_finance as yf

TODAY = dt.date(2026, 10, 21)
KEY = "secret-key"


def _row(date, open_=1.0, high=2.0, low=0.5, close=1.5, adj=1.4, volume=10):
    return {"date": date, "open": open_, "high": high, "low": low, "close": close,
            "adj_close": adj, "volume": volume}


class TestRoute:
    @pytest.mark.parametrize("symbol, expected", [
        ("AAPL", ("eodhd", "AAPL.US", "USA Stocks", "USD")),
        ("brk-b", ("eodhd", "BRK-B.US", "USA Stocks", "USD")),
        ("VOD.L", ("eodhd", "VOD.LSE", "London Exchange", "GBp")),
        ("SAP.DE", ("eodhd", "SAP.XETRA", "XETRA Stock Exchange", "EUR")),
        ("MC.PA", ("eodhd", "MC.PA", "Euronext Paris", "EUR")),
        ("RY.TO", ("eodhd", "RY.TO", "Toronto Exchange", "CAD")),
        ("BHP.AX", ("eodhd", "BHP.AU", "Australian Securities Exchange", "AUD")),
        ("0700.HK", ("eodhd", "0700.HK", "Hong Kong Exchange", "HKD")),
        ("RELIANCE.NS", ("alphavantage", "RELIANCE.BSE", "BSE", "INR")),
        ("RELIANCE.BO", ("alphavantage", "RELIANCE.BSE", "BSE", "INR")),
        ("^GSPC", ("eodhd", "GSPC.INDX", "Index", "points")),
        ("EURUSD=X", ("eodhd", "EURUSD.FOREX", "Currency", "USD")),
        ("JPY=X", ("eodhd", "USDJPY.FOREX", "Currency", "JPY")),
        ("BTC-USD", ("eodhd", "BTC-USD.CC", "Cryptocurrency", "USD")),
    ])
    def test_routes(self, symbol, expected):
        assert ps.route(symbol) == expected

    @pytest.mark.parametrize("symbol, message", [
        ("D05.SI", "Singapore listings"),
        ("7203.T", "Tokyo listings"),
        ("GC=F", "futures"),
        ("ENI.MI", "suffix .MI"),
    ])
    def test_refused(self, symbol, message):
        with pytest.raises(ValueError, match=message):
            ps.route(symbol)


class TestWindow:
    def test_period_bounds(self):
        params = yf.build_params(start="2026-01-02", end="2026-02-03")
        assert ps.window(params) == (dt.date(2026, 1, 2), dt.date(2026, 2, 3), None)

    def test_last_window_ends_today(self):
        params = yf.build_params(last=5)
        first, final, keep = ps.window(params)
        assert final == dt.datetime.now(dt.timezone.utc).date() and keep is None
        assert (final - first).days == 20

    @pytest.mark.parametrize("range_, first, keep", [
        ("5d", TODAY - dt.timedelta(days=12), 5),
        ("1mo", TODAY - dt.timedelta(days=31), None),
        ("6mo", TODAY - dt.timedelta(days=183), None),
        ("1y", TODAY - dt.timedelta(days=366), None),
        ("ytd", dt.date(2026, 1, 1), None),
        ("max", ps.EARLIEST, None),
    ])
    def test_ranges(self, range_, first, keep):
        assert ps.window({"range": range_}, today=TODAY) == (first, TODAY, keep)

    def test_every_valid_range_handled(self):
        for range_ in yf.VALID_RANGES:
            ps.window({"range": range_}, today=TODAY)

    def test_unknown_range(self):
        with pytest.raises(ValueError, match="unsupported range"):
            ps.window({"range": "3d"}, today=TODAY)


class TestAggregate:
    def test_daily_unchanged(self):
        rows = [_row("2026-10-19")]
        assert ps.aggregate(rows, "1d") is rows

    def test_weekly(self):
        rows = [_row("2026-10-14", open_=1, high=3, low=1, close=2, adj=1.9, volume=5),
                _row("2026-10-16", open_=2, high=4, low=0.5, close=3, adj=2.9, volume=None),
                _row("2026-10-19", open_=3, high=3, low=3, close=3, adj=3, volume=7)]
        bars = ps.aggregate(rows, "1wk")
        assert bars == [
            {"date": "2026-10-12", "open": 1, "high": 4, "low": 0.5, "close": 3,
             "adj_close": 2.9, "volume": 5},
            {"date": "2026-10-19", "open": 3, "high": 3, "low": 3, "close": 3,
             "adj_close": 3, "volume": 7},
        ]

    def test_monthly_and_missing_values(self):
        rows = [_row("2026-09-30", open_=None, volume=None),
                _row("2026-10-01", high=None), _row("2026-10-20", high=5)]
        bars = ps.aggregate(rows, "1mo")
        assert [b["date"] for b in bars] == ["2026-09-01", "2026-10-01"]
        assert bars[0]["open"] is None and bars[0]["volume"] is None
        assert bars[1]["high"] == 5 and bars[1]["volume"] == 20

    def test_unknown_interval(self):
        with pytest.raises(ValueError, match="unsupported interval"):
            ps.aggregate([], "1h")


class TestDailyHistory:
    @pytest.fixture(autouse=True)
    def keys(self, monkeypatch):
        monkeypatch.setattr(ps, "load_dotenv", lambda *a, **k: None)
        monkeypatch.setattr(ps, "_last_alphavantage_call", 0.0)
        monkeypatch.setenv("EODHD_API_KEY", KEY)
        monkeypatch.setenv("ALPHAVANTAGE_API_KEY", KEY)

    def _eod(self, monkeypatch, bars):
        calls = []

        def fake(symbol, first, final, key):
            calls.append((symbol, first, final, key))
            return bars

        monkeypatch.setattr(eodph, "fetch_eod", fake)
        return calls

    @staticmethod
    def _bar(date, close=10.0, **extra):
        bar = {"date": date, "open": 9.0, "high": 11.0, "low": 8.0, "close": close,
               "adjusted_close": close, "volume": 100}
        bar.update(extra)
        return bar

    def test_eodhd_dispatch_window_and_notes(self, monkeypatch):
        warning = "Data is limited by one year as you have free subscription"
        calls = self._eod(monkeypatch, [self._bar("2025-10-21", warning=warning),
                                        self._bar("2026-01-05")])
        params = yf.build_params(start="2026-01-01", end="2026-01-31")
        history = ps.daily_history("VOD.L", params)
        assert calls == [("VOD.LSE", dt.date(2026, 1, 1), dt.date(2026, 1, 31), KEY)]
        assert (history["source"], history["notes"]) == ("EODHD", [warning])
        assert (history["symbol"], history["exchange"], history["currency"]) == (
            "VOD.L", "London Exchange", "GBp")
        assert [b["date"] for b in history["bars"]] == ["2026-01-05"]  # out-of-window bar dropped

    def test_bars_are_neutral_rows(self, monkeypatch):
        self._eod(monkeypatch, [self._bar("2026-01-05", close=10.123456789)])
        history = ps.daily_history("AAPL", yf.build_params(start="2026-01-01", end="2026-01-31"))
        # daily_prices.price_row() has already rounded the provider's figures to 4 places.
        assert history["bars"] == [{"date": "2026-01-05", "open": 9.0, "high": 11.0, "low": 8.0,
                                    "close": 10.1235, "adj_close": 10.1235, "volume": 100}]

    def test_five_day_range_keeps_five(self, monkeypatch):
        today = dt.datetime.now(dt.timezone.utc).date()
        dates = [(today - dt.timedelta(days=i)).isoformat() for i in range(8, -1, -1)]
        self._eod(monkeypatch, [self._bar(d) for d in dates])
        history = ps.daily_history("AAPL", {"range": "5d", "interval": "1d"})
        assert len(history["bars"]) == 5

    def test_weekly_interval_aggregates(self, monkeypatch):
        self._eod(monkeypatch, [self._bar("2026-10-13"), self._bar("2026-10-14", close=12.0)])
        params = yf.build_params(interval="1wk", start="2026-10-01", end="2026-10-20")
        history = ps.daily_history("AAPL", params)
        assert [(b["date"], b["close"]) for b in history["bars"]] == [("2026-10-12", 12.0)]

    def test_alphavantage_dispatch_and_history_note(self, monkeypatch):
        series = {(dt.date(2026, 6, 1) + dt.timedelta(days=i)).isoformat():
                  {"1. open": "1", "2. high": "2", "3. low": "1", "4. close": "1.5",
                   "5. volume": "10"} for i in range(100)}
        calls = []

        def fake(symbol, key, full=False):
            calls.append((symbol, key, full))
            return {avph.SERIES_KEY: series}

        monkeypatch.setattr(avph, "fetch_daily", fake)
        history = ps.daily_history("RELIANCE.NS", yf.build_params(start="2026-01-01"))
        assert calls == [("RELIANCE.BSE", KEY, False)]
        assert history["source"] == "Alpha Vantage"
        assert "latest 100 sessions" in history["notes"][0]
        assert history["bars"][0]["adj_close"] is None

    def test_provider_error_named_and_redacted(self, monkeypatch):
        def boom(symbol, first, final, key):
            raise requests.ConnectionError(f"failed: ?api_token={key}")

        monkeypatch.setattr(eodph, "fetch_eod", boom)
        with pytest.raises(requests.RequestException) as exc:
            ps.daily_history("AAPL", {"range": "1mo"})
        message = str(exc.value)
        assert message.startswith("EODHD (AAPL.US):")
        assert KEY not in message and "<redacted>" in message

    def test_not_found_becomes_request_exception(self, monkeypatch):
        def missing(symbol, first, final, key):
            raise ValueError("HTTP 404: Ticker Not Found.")

        monkeypatch.setattr(eodph, "fetch_eod", missing)
        with pytest.raises(requests.RequestException, match="Ticker Not Found"):
            ps.daily_history("NOPE", {"range": "1mo"})

    def test_alphavantage_calls_spaced(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr(ps.time, "sleep", sleeps.append)
        monkeypatch.setattr(ps.time, "monotonic", lambda: 100.0)
        monkeypatch.setattr(ps, "_last_alphavantage_call", 99.5)
        monkeypatch.setattr(avph, "fetch_daily", lambda symbol, key, full=False: {
            avph.SERIES_KEY: {"2026-10-20": {"4. close": "1"}}})
        ps.daily_history("RELIANCE.NS", {"range": "1mo"})
        assert sleeps == [pytest.approx(0.6)]
        assert ps._last_alphavantage_call == 100.0

    def test_missing_key(self, monkeypatch):
        monkeypatch.delenv("ALPHAVANTAGE_API_KEY")
        with pytest.raises(ValueError, match="ALPHAVANTAGE_API_KEY must be set"):
            ps.daily_history("RELIANCE.NS", {"range": "1mo"})

    def test_unsupported_symbol_before_any_call(self, monkeypatch):
        calls = self._eod(monkeypatch, [])
        with pytest.raises(ValueError, match="Singapore"):
            ps.daily_history("D05.SI", {"range": "1mo"})
        assert calls == []
