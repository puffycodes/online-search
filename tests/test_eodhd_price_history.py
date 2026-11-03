"""Tests for eodhd_price_history: fetch_eod request/errors, extract_rows, main() output/exit paths."""

import datetime as dt
import json

import pytest
import requests

import daily_prices
import eodhd_price_history as eod
from helpers import FakeResponse

KEY = "secret-key"


def _bar(date, close=10.0, **extra):
    bar = {"date": date, "open": 9.5, "high": 10.5, "low": 9.0, "close": close,
           "adjusted_close": close, "volume": 100}
    bar.update(extra)
    return bar


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setattr(eod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("EODHD_API_KEY", KEY)


class TestFetchEod:
    def test_request(self, monkeypatch):
        calls = []

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(json_data=[_bar("2026-10-20")])

        monkeypatch.setattr(eod.requests, "get", fake_get)
        payload = eod.fetch_eod("AAPL.US", dt.date(2026, 10, 1), dt.date(2026, 10, 20), KEY)
        assert payload[0]["date"] == "2026-10-20"
        url, kwargs = calls[0]
        assert url == "https://eodhd.com/api/eod/AAPL.US"
        assert kwargs["params"] == {"api_token": KEY, "fmt": "json", "period": "d",
                                    "from": "2026-10-01", "to": "2026-10-20"}
        assert kwargs["timeout"] == eod.REQUEST_TIMEOUT

    def test_not_found(self, monkeypatch):
        monkeypatch.setattr(eod.requests, "get", lambda url, **k: FakeResponse(
            status_code=404, text="Ticker Not Found."))
        with pytest.raises(ValueError, match="HTTP 404: Ticker Not Found."):
            eod.fetch_eod("X.SG", dt.date(2026, 1, 1), dt.date(2026, 1, 2), KEY)

    def test_non_list_body(self, monkeypatch):
        monkeypatch.setattr(eod.requests, "get", lambda url, **k: FakeResponse(
            json_data={"message": "odd"}))
        with pytest.raises(ValueError, match="unexpected response"):
            eod.fetch_eod("X.US", dt.date(2026, 1, 1), dt.date(2026, 1, 2), KEY)


class TestExtractRows:
    def test_sorted_and_shaped(self):
        rows, notes = eod.extract_rows([_bar("2026-10-02"), _bar("2026-10-01", close=9.87654)])
        assert [r["date"] for r in rows] == ["2026-10-01", "2026-10-02"]
        assert rows[0]["close"] == 9.8765 and rows[0]["adj_close"] == 9.8765
        assert notes == []

    def test_skips_bar_without_close(self):
        rows, _ = eod.extract_rows([_bar("2026-10-01", close=None), _bar("2026-10-02")])
        assert [r["date"] for r in rows] == ["2026-10-02"]

    def test_warning_becomes_one_note(self):
        warning = "Data is limited by one year as you have free subscription"
        rows, notes = eod.extract_rows([_bar("2025-10-21", warning=warning),
                                        _bar("2025-10-22", warning=warning)])
        assert notes == [warning]
        assert len(rows) == 2


class TestMain:
    def _wire(self, monkeypatch, bars):
        monkeypatch.setattr(eod, "fetch_eod", lambda symbol, first, final, key: bars)
        monkeypatch.setattr(daily_prices.dt, "date", _FixedDate)

    def test_json_last_trims(self, monkeypatch, capsys, api_key):
        self._wire(monkeypatch, [_bar(f"2026-10-{d:02d}") for d in range(14, 21)])
        eod.main(["AAPL.US", "--last", "2", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["symbol"] == "AAPL.US" and payload["source"] == "EODHD"
        assert payload["notes"] == []
        assert [r["date"] for r in payload["prices"]] == ["2026-10-19", "2026-10-20"]

    def test_out_of_window_bar_dropped_with_note(self, monkeypatch, capsys, api_key):
        warning = "Data is limited by one year as you have free subscription"
        self._wire(monkeypatch, [_bar("2025-10-21", warning=warning)])
        eod.main(["AAPL.US", "--start", "2024-01-01", "--end", "2024-01-10"])
        out = capsys.readouterr().out
        assert f"Note: {warning}" in out
        assert "No settled price data found for AAPL.US." in out

    def test_text_table(self, monkeypatch, capsys, api_key):
        self._wire(monkeypatch, [_bar("2026-10-20")])
        eod.main(["AAPL.US"])
        out = capsys.readouterr().out
        assert "AAPL.US - EODHD - 1 session(s)" in out

    def test_fetch_error_redacts_key(self, monkeypatch, capsys, api_key):
        def boom(symbol, first, final, key):
            raise requests.ConnectionError(f"failed: https://eodhd.com/api/eod/X?api_token={key}")

        monkeypatch.setattr(eod, "fetch_eod", boom)
        with pytest.raises(SystemExit) as exc:
            eod.main(["X.US", "--json"])
        assert exc.value.code == 1
        error = json.loads(capsys.readouterr().err)["error"]
        assert KEY not in error and "<redacted>" in error

    def test_missing_key_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(eod, "load_dotenv", lambda *a, **k: None)
        monkeypatch.delenv("EODHD_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            eod.main(["AAPL.US", "--json"])
        assert exc.value.code == 1
        assert "EODHD_API_KEY" in json.loads(capsys.readouterr().err)["error"]

    def test_invalid_date_exits_1_before_key_check(self, monkeypatch, capsys):
        monkeypatch.delenv("EODHD_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            eod.main(["AAPL.US", "--start", "not-a-date", "--json"])
        assert exc.value.code == 1
        assert "invalid date" in json.loads(capsys.readouterr().err)["error"]

    def test_last_zero_rejected_at_parse_time(self):
        with pytest.raises(SystemExit) as exc:
            eod.main(["AAPL.US", "--last", "0"])
        assert exc.value.code == 2


class _FixedDate(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)
