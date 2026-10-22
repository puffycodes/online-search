"""Tests for stock_price_history: extract_rows row shaping from stock_data's neutral
daily history, and main() output/exit paths."""

import json

import pytest
import requests

import stock_data
import stock_price_history as sch
import yahoo_finance as yf


def _bar(date, open_=10.0, high=10.5, low=9.5, close=10.25, adj=10.2, volume=1000):
    return {"date": date, "open": open_, "high": high, "low": low, "close": close,
            "adj_close": adj, "volume": volume}


def _history(bars=None, **changes):
    """A neutral stock_data.daily_history() result."""
    history = {
        "source": "EODHD", "notes": [], "symbol": "AAA", "exchange": "Test", "currency": "USD",
        "bars": bars if bars is not None else [
            _bar("2024-01-01"),
            _bar("2024-01-02", 11.0, 11.5, 10.5, 11.25, 11.2, 2000),
            _bar("2024-01-03", 12.0, 12.5, 11.5, None, None, None),
        ],
    }
    history.update(changes)
    return history


class TestExtractRows:
    def test_skips_unsettled_close(self):
        rows = sch.extract_rows(_history())
        assert [r["date"] for r in rows] == ["2024-01-01", "2024-01-02"]

    def test_rounds_to_4dp(self):
        rows = sch.extract_rows(_history([_bar("2024-01-01", open_=10.123456)]))
        assert rows[0]["open"] == 10.1235

    def test_volume_int_and_none_safe(self):
        rows = sch.extract_rows(_history([_bar("2024-01-01", volume=1000.0),
                                          _bar("2024-01-02", volume=None)]))
        assert rows[0]["volume"] == 1000 and isinstance(rows[0]["volume"], int)
        assert rows[1]["volume"] is None

    def test_missing_adjclose_is_none(self):
        assert sch.extract_rows(_history([_bar("2024-01-01", adj=None)]))[0]["adj_close"] is None

    def test_row_keys(self):
        assert list(sch.extract_rows(_history())[0]) == [
            "date", "open", "high", "low", "close", "adj_close", "volume"]


class TestMain:
    def _wire(self, monkeypatch, rows, **changes):
        monkeypatch.setattr(yf, "build_params", lambda **k: {})
        monkeypatch.setattr(stock_data, "daily_history",
                            lambda sym, params: _history(**{"source": None, **changes}))
        monkeypatch.setattr(sch, "extract_rows", lambda history: list(rows))

    def test_last_trims_rows_json(self, monkeypatch, capsys):
        rows = [{"date": "2024-01-0%d" % i, "open": i, "high": i, "low": i, "close": i,
                 "adj_close": i, "volume": i} for i in range(1, 6)]
        self._wire(monkeypatch, rows)
        sch.main(["AAA", "--last", "2", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert [r["date"] for r in payload["prices"]] == ["2024-01-04", "2024-01-05"]

    def test_source_and_notes(self, monkeypatch, capsys):
        rows = [{"date": "2024-01-01", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                 "adj_close": 1.0, "volume": 10}]
        self._wire(monkeypatch, rows, source="EODHD", notes=["limited to one year"])
        sch.main(["AAA", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["source"] == "EODHD" and payload["notes"] == ["limited to one year"]
        sch.main(["AAA"])
        out = capsys.readouterr().out
        assert "Note: limited to one year" in out and "- EODHD - 1 session(s)" in out

    def test_fetch_error_exits_json(self, monkeypatch, capsys):
        def boom(sym, params):
            raise requests.RequestException("delisted")

        monkeypatch.setattr(yf, "build_params", lambda **k: {})
        monkeypatch.setattr(stock_data, "daily_history", boom)
        with pytest.raises(SystemExit):
            sch.main(["AAA", "--json"])
        assert json.loads(capsys.readouterr().err)["error"].endswith("delisted")

    def test_header_from_the_history(self, monkeypatch, capsys):
        self._wire(monkeypatch, [_bar("2024-01-01")], exchange=None, source="EODHD")
        sch.main(["aaa"])
        assert "AAA - ? (USD) - EODHD - 1 session(s)" in capsys.readouterr().out

    def test_empty_rows_text(self, monkeypatch, capsys):
        self._wire(monkeypatch, [])
        sch.main(["AAA"])
        assert "No settled price data" in capsys.readouterr().out

    def test_adj_close_column_shown_when_differs(self, monkeypatch, capsys):
        rows = [{"date": "2024-01-01", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                 "adj_close": 0.9, "volume": 10}]
        self._wire(monkeypatch, rows)
        sch.main(["AAA"])
        assert "Adj Close" in capsys.readouterr().out

    def test_last_zero_rejected_at_parse_time(self):
        with pytest.raises(SystemExit) as exc:
            sch.main(["AAA", "--last", "0"])
        assert exc.value.code == 2

    def test_invalid_start_date_exits_1_json(self, capsys):
        # No monkeypatching: build_params/parse_date rejects the date before
        # any network call, so this exercises the real error path.
        with pytest.raises(SystemExit) as exc:
            sch.main(["AAA", "--start", "not-a-date", "--json"])
        assert exc.value.code == 1
        assert "invalid date" in json.loads(capsys.readouterr().err)["error"]
