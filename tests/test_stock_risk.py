"""Tests for stock_risk: close extraction, annualization, per-symbol figures, pairing and main()."""

import datetime as dt
import json

import pytest
import requests

import stock_risk as sr
import price_source
import yahoo_finance as yf

MON = dt.date(2024, 1, 1)  # a Monday


def _days(*offsets):
    return [MON + dt.timedelta(days=n) for n in offsets]


def _rows(prices, offsets=None):
    offsets = offsets if offsets is not None else range(len(prices))
    return list(zip(_days(*offsets), prices))


class TestExtractCloses:
    def test_prefers_adjusted_close(self, chart_result):
        _, rows, basis = sr.extract_closes(chart_result)
        assert basis == "adj_close"
        assert [p for _, p in rows] == [10.1, 11.1, 12.1]
        assert [d for d, _ in rows] == _days(0, 1, 2)

    def test_falls_back_to_close_without_adjclose(self, chart_result):
        del chart_result["indicators"]["adjclose"]
        _, rows, basis = sr.extract_closes(chart_result)
        assert basis == "close"
        assert [p for _, p in rows] == [10.2, 11.2, 12.2]

    def test_one_missing_adjclose_uses_close_throughout(self, chart_result):
        # Mixing the two bases in one series would invent a jump.
        chart_result["indicators"]["adjclose"][0]["adjclose"] = [10.1, None, 12.1]
        _, rows, basis = sr.extract_closes(chart_result)
        assert basis == "close"
        assert [p for _, p in rows] == [10.2, 11.2, 12.2]

    def test_skips_unsettled_close(self, chart_result):
        chart_result["indicators"]["quote"][0]["close"] = [10.2, None, 12.2]
        _, rows, basis = sr.extract_closes(chart_result)
        assert [d for d, _ in rows] == _days(0, 2)
        assert basis == "adj_close"

    def test_gmtoffset_shifts_date(self, chart_result):
        chart_result["meta"]["gmtoffset"] = -3600
        _, rows, _ = sr.extract_closes(chart_result)
        assert rows[0][0] == dt.date(2023, 12, 31)

    def test_empty_result(self):
        _, rows, basis = sr.extract_closes({"meta": {}})
        assert rows == []
        assert basis == "close"


class TestPeriodsPerYear:
    def test_weekdays_only_is_trading_days(self):
        assert sr.periods_per_year(_days(0, 1, 2, 3, 4, 7)) == 252

    def test_any_weekend_session_is_calendar_days(self):
        assert sr.periods_per_year(_days(4, 5, 6, 7)) == 365


class TestSummarize:
    META = {"symbol": "AAA", "fullExchangeName": "Test", "currency": "USD"}

    def test_reference_figures(self):
        out = sr.summarize("aaa", self.META, _rows([100, 120, 90, 110]), "close")
        assert out["symbol"] == "AAA"
        assert (out["sessions"], out["start"], out["end"]) == (4, "2024-01-01", "2024-01-04")
        assert (out["first"], out["last"]) == (100, 110)
        assert out["change"] == pytest.approx(0.10)
        assert out["periods_per_year"] == 252
        assert out["volatility"] > 0
        assert out["max_drawdown"] == {
            "drawdown": -0.25,
            "peak_date": "2024-01-02", "peak": 120,
            "trough_date": "2024-01-03", "trough": 90,
            "recovery_date": None,
        }
        assert (out["high_date"], out["high"]) == ("2024-01-02", 120)
        assert out["from_high"] == pytest.approx(110 / 120 - 1)

    def test_recovery_date(self):
        out = sr.summarize("AAA", self.META, _rows([100, 50, 100]), "close")
        assert out["max_drawdown"]["recovery_date"] == "2024-01-03"

    def test_no_fall_has_null_dates(self):
        out = sr.summarize("AAA", self.META, _rows([1, 2, 3]), "close")
        assert out["max_drawdown"] == {
            "drawdown": 0.0, "peak_date": None, "peak": None,
            "trough_date": None, "trough": None, "recovery_date": None,
        }
        assert out["from_high"] == 0.0

    def test_too_short_for_volatility(self):
        out = sr.summarize("AAA", self.META, _rows([100, 101]), "close")
        assert out["volatility"] is None

    def test_weekend_series_annualizes_over_365(self):
        rows = _rows([100, 102, 99, 103], offsets=[4, 5, 6, 7])
        out = sr.summarize("BTC-USD", {}, rows, "close")
        assert out["periods_per_year"] == 365
        assert out["volatility"] == pytest.approx(
            sr.volatility([100, 102, 99, 103], 365))

    def test_symbol_falls_back_to_argument(self):
        assert sr.summarize("bbb", {}, _rows([1, 2, 3]), "close")["symbol"] == "bbb"


class TestPairCorrelation:
    def test_aligns_on_shared_dates(self):
        # B has no session on day 2, and an extra one on day 5; A's day-2
        # price would wreck the +1 correlation if it weren't dropped.
        a = _rows([100, 150, 999, 75, 150], offsets=[0, 1, 2, 3, 4])
        b = _rows([10, 15, 7.5, 15, 1], offsets=[0, 1, 3, 4, 5])
        out = sr.pair_correlation("A", a, "B", b)
        assert out["sessions"] == 4
        assert (out["start"], out["end"]) == ("2024-01-01", "2024-01-05")
        assert out["correlation"] == pytest.approx(1.0)

    def test_too_few_shared_sessions_is_none(self):
        out = sr.pair_correlation("A", _rows([1, 2, 3]), "B", _rows([1, 2], [2, 3]))
        assert out["sessions"] == 1
        assert out["correlation"] is None

    def test_no_shared_sessions(self):
        out = sr.pair_correlation("A", _rows([1, 2, 3]), "B", _rows([1, 2, 3], [7, 8, 9]))
        assert (out["sessions"], out["start"], out["end"], out["correlation"]) == (
            0, None, None, None)


class TestParseArgs:
    def test_defaults(self):
        args = sr.parse_args(["AAA"])
        assert args.range == "1y"
        assert args.benchmark is None
        assert args.json is False

    def test_drops_repeated_symbols(self):
        assert sr.parse_args(["AAA", "aaa", "BBB"]).symbols == ["AAA", "BBB"]

    def test_benchmark_also_listed_is_measured_once(self):
        args = sr.parse_args(["AAA", "^gspc", "--benchmark", "^GSPC"])
        assert args.symbols == ["AAA"]

    def test_only_the_benchmark_exits_2(self, capsys):
        with pytest.raises(SystemExit) as exc:
            sr.parse_args(["^GSPC", "--benchmark", "^GSPC"])
        assert exc.value.code == 2
        assert "besides the --benchmark" in capsys.readouterr().err

    def test_missing_symbol_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            sr.parse_args([])
        assert exc.value.code == 2

    def test_range_and_last_exclusive(self):
        with pytest.raises(SystemExit) as exc:
            sr.parse_args(["AAA", "--range", "1y", "--last", "5"])
        assert exc.value.code == 2


class TestMain:
    DATA = {
        "AAA": [100, 150, 75, 90],
        "BBB": [10, 15, 7.5, 9],
        "^GSPC": [1000, 900, 950, 1000],
    }

    def _wire(self, monkeypatch, data=None, fail=()):
        data = self.DATA if data is None else data

        def load(symbol, params, last):
            if symbol in fail:
                return "failed to fetch prices: nope"
            rows = _rows(data[symbol])
            rows = rows[-last:] if last else rows
            return {"symbol": symbol, "fullExchangeName": "Test", "currency": "USD"}, rows, "close"

        monkeypatch.setattr(yf, "build_params", lambda **k: {})
        monkeypatch.setattr(sr, "load_symbol", load)

    def test_json_shape(self, monkeypatch, capsys):
        self._wire(monkeypatch)
        sr.main(["AAA", "BBB", "--benchmark", "^GSPC", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert [s["symbol"] for s in payload["symbols"]] == ["AAA", "BBB"]
        assert payload["benchmark"]["symbol"] == "^GSPC"
        assert [(p["a"], p["b"]) for p in payload["correlations"]] == [
            ("AAA", "BBB"), ("AAA", "^GSPC"), ("BBB", "^GSPC"),
        ]
        assert payload["correlations"][0]["correlation"] == pytest.approx(1.0)
        assert payload["skipped"] == []

    def test_single_symbol_has_no_pairs(self, monkeypatch, capsys):
        self._wire(monkeypatch)
        sr.main(["AAA", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["correlations"] == []
        assert payload["benchmark"] is None

    def test_last_trims_rows(self, monkeypatch, capsys):
        self._wire(monkeypatch)
        sr.main(["AAA", "--last", "2", "--json"])
        assert json.loads(capsys.readouterr().out)["symbols"][0]["sessions"] == 2

    def test_failed_symbol_is_skipped(self, monkeypatch, capsys):
        self._wire(monkeypatch, fail=("BBB",))
        sr.main(["AAA", "BBB", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert [s["symbol"] for s in payload["symbols"]] == ["AAA"]
        assert payload["skipped"] == [{"symbol": "BBB", "reason": "failed to fetch prices: nope"}]

    def test_failed_benchmark_is_skipped(self, monkeypatch, capsys):
        self._wire(monkeypatch, fail=("^GSPC",))
        sr.main(["AAA", "--benchmark", "^GSPC", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["benchmark"] is None
        assert payload["skipped"][0]["symbol"] == "^GSPC"

    def test_all_symbols_fail_exits_1_json(self, monkeypatch, capsys):
        self._wire(monkeypatch, fail=("AAA", "BBB"))
        with pytest.raises(SystemExit) as exc:
            sr.main(["AAA", "BBB", "--json"])
        assert exc.value.code == 1
        assert "no price data for any symbol" in json.loads(capsys.readouterr().err)["error"]

    def test_benchmark_alone_with_data_is_not_enough(self, monkeypatch, capsys):
        self._wire(monkeypatch, fail=("AAA",))
        with pytest.raises(SystemExit) as exc:
            sr.main(["AAA", "--benchmark", "^GSPC", "--json"])
        assert exc.value.code == 1

    def test_text_report(self, monkeypatch, capsys):
        self._wire(monkeypatch, fail=("BBB",))
        sr.main(["AAA", "BBB", "--benchmark", "^GSPC"])
        captured = capsys.readouterr()
        assert captured.out.startswith("Measuring risk for AAA, BBB, ^GSPC...")
        assert "^GSPC (benchmark)" in captured.out
        assert "worst fall  : -50.0%  2024-01-02" in captured.out
        assert "AAA / ^GSPC" in captured.out
        assert "don't predict" in captured.out
        assert "Warning: skipped 'BBB'" in captured.err

    def test_text_report_no_fall(self, monkeypatch, capsys):
        self._wire(monkeypatch, data={"AAA": [1, 2, 3]})
        sr.main(["AAA"])
        assert "none (never closed below an earlier high)" in capsys.readouterr().out

    def test_last_zero_rejected_at_parse_time(self):
        with pytest.raises(SystemExit) as exc:
            sr.main(["AAA", "--last", "0"])
        assert exc.value.code == 2

    def test_invalid_start_date_exits_1_json(self, capsys):
        # No monkeypatching: build_params rejects the date before any network call.
        with pytest.raises(SystemExit) as exc:
            sr.main(["AAA", "--start", "not-a-date", "--json"])
        assert exc.value.code == 1
        assert "invalid date" in json.loads(capsys.readouterr().err)["error"]


class TestLoadSymbol:
    def test_fetch_error_is_reason(self, monkeypatch):
        def boom(symbol, params):
            raise requests.RequestException("symbol may be delisted")

        monkeypatch.setattr(price_source, "fetch_history", boom)
        assert sr.load_symbol("AAA", {}, None) == (
            "failed to fetch prices: symbol may be delisted")

    def test_no_rows_is_reason(self, monkeypatch, chart_result):
        chart_result["indicators"]["quote"][0]["close"] = [None, None, None]
        monkeypatch.setattr(price_source, "fetch_history", lambda symbol, params: chart_result)
        assert sr.load_symbol("AAA", {}, None) == "no settled price data in the window"

    def test_non_positive_price_is_reason(self, monkeypatch, chart_result):
        chart_result["indicators"]["adjclose"][0]["adjclose"] = [10.1, 0.0, 12.1]
        monkeypatch.setattr(price_source, "fetch_history", lambda symbol, params: chart_result)
        assert sr.load_symbol("AAA", {}, None) == "non-positive prices in the window"

    def test_last_trims(self, monkeypatch, chart_result):
        monkeypatch.setattr(price_source, "fetch_history", lambda symbol, params: chart_result)
        _, rows, _ = sr.load_symbol("AAA", {}, 2)
        assert [d for d, _ in rows] == _days(1, 2)
