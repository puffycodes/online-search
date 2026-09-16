"""Tests for stock_close_history: extract_rows row shaping and main() output/exit paths."""

import json

import pytest
import requests

import stock_close_history as sch
import yahoo_finance as yf


def _result(**overrides):
    base = {
        "meta": {"symbol": "AAA", "fullExchangeName": "Test", "currency": "USD", "gmtoffset": 0},
        "timestamp": [1704067200, 1704153600, 1704240000],
        "indicators": {
            "quote": [{
                "open": [10.0, 11.0, 12.0],
                "high": [10.5, 11.5, 12.5],
                "low": [9.5, 10.5, 11.5],
                "close": [10.25, 11.25, None],
                "volume": [1000, 2000, None],
            }],
            "adjclose": [{"adjclose": [10.2, 11.2, None]}],
        },
    }
    base.update(overrides)
    return base


class TestExtractRows:
    def test_skips_unsettled_close(self):
        _, rows = sch.extract_rows(_result())
        assert [r["date"] for r in rows] == ["2024-01-01", "2024-01-02"]

    def test_rounds_to_4dp(self):
        res = _result()
        res["indicators"]["quote"][0]["open"] = [10.123456, 11.0, 12.0]
        _, rows = sch.extract_rows(res)
        assert rows[0]["open"] == 10.1235

    def test_volume_int_and_none_safe(self):
        _, rows = sch.extract_rows(_result())
        assert rows[0]["volume"] == 1000
        assert isinstance(rows[0]["volume"], int)

    def test_missing_adjclose_is_none(self):
        res = _result()
        del res["indicators"]["adjclose"]
        _, rows = sch.extract_rows(res)
        assert rows[0]["adj_close"] is None

    def test_gmtoffset_shifts_date(self):
        res = _result()
        res["meta"]["gmtoffset"] = -3600
        res["timestamp"] = [1704067200]  # 2024-01-01 00:00 UTC -> 2023-12-31 local
        res["indicators"]["quote"][0] = {
            "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1],
        }
        res["indicators"]["adjclose"] = [{"adjclose": [1.0]}]
        _, rows = sch.extract_rows(res)
        assert rows[0]["date"] == "2023-12-31"


class TestMain:
    def _wire(self, monkeypatch, rows, meta=None):
        monkeypatch.setattr(yf, "build_params", lambda **k: {})
        monkeypatch.setattr(yf, "fetch_history", lambda sym, params: object())
        monkeypatch.setattr(sch, "extract_rows", lambda result: (meta or {"symbol": "AAA"}, list(rows)))

    def test_last_trims_rows_json(self, monkeypatch, capsys):
        rows = [{"date": "2024-01-0%d" % i, "open": i, "high": i, "low": i, "close": i,
                 "adj_close": i, "volume": i} for i in range(1, 6)]
        self._wire(monkeypatch, rows)
        sch.main(["AAA", "--last", "2", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert [r["date"] for r in payload["prices"]] == ["2024-01-04", "2024-01-05"]

    def test_fetch_error_exits_json(self, monkeypatch, capsys):
        def boom(sym, params):
            raise requests.RequestException("delisted")

        monkeypatch.setattr(yf, "build_params", lambda **k: {})
        monkeypatch.setattr(yf, "fetch_history", boom)
        with pytest.raises(SystemExit):
            sch.main(["AAA", "--json"])
        assert json.loads(capsys.readouterr().err)["error"].endswith("delisted")

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
