"""Tests for stock_candlestick_chart: the --ma / --flip-ma arg parsers and extract_rows
(from stock_data's neutral daily history)."""

import argparse
import datetime as dt

import pytest

import stock_candlestick_chart as scdl


class TestParseMaArg:
    def test_sorted_and_deduplicated(self):
        assert scdl._parse_ma_arg("50,20,10,5,20") == [5, 10, 20, 50]

    @pytest.mark.parametrize("raw", ["", "none", "off", "  NONE  ", "Off"])
    def test_disable_values(self, raw):
        assert scdl._parse_ma_arg(raw) == []

    def test_skips_empty_parts(self):
        assert scdl._parse_ma_arg("5, ,10") == [5, 10]

    @pytest.mark.parametrize("raw", ["3,-1", "0,5"])
    def test_non_positive_rejected(self, raw):
        with pytest.raises(argparse.ArgumentTypeError, match="positive"):
            scdl._parse_ma_arg(raw)

    def test_non_integer_rejected(self):
        with pytest.raises(argparse.ArgumentTypeError, match="comma-separated integers"):
            scdl._parse_ma_arg("a,b")


class TestParseFlipMaArg:
    def test_pair_order_preserved(self):
        assert scdl._parse_flip_ma_arg("50,20") == (50, 20)

    @pytest.mark.parametrize("raw", ["", "none", "off"])
    def test_disable_values(self, raw):
        assert scdl._parse_flip_ma_arg(raw) is None

    @pytest.mark.parametrize("raw", ["20", "20,50,100"])
    def test_needs_exactly_two(self, raw):
        with pytest.raises(argparse.ArgumentTypeError, match="exactly two"):
            scdl._parse_flip_ma_arg(raw)

    def test_non_positive_rejected(self):
        with pytest.raises(argparse.ArgumentTypeError, match="positive"):
            scdl._parse_flip_ma_arg("0,50")

    def test_non_integer_rejected(self):
        with pytest.raises(argparse.ArgumentTypeError, match="two comma-separated integers"):
            scdl._parse_flip_ma_arg("a,b")


class TestExtractRows:
    def _history(self):
        """A neutral stock_data.daily_history() result; the third bar has no open."""
        def bar(date, o, h, low, c, v):
            return {"date": date, "open": o, "high": h, "low": low, "close": c,
                    "adj_close": c, "volume": v}

        return {"source": "EODHD", "notes": [], "symbol": "AAA", "exchange": "X",
                "currency": "USD", "bars": [
                    bar("2024-01-01", 10.0, 10.5, 9.5, 10.2, 1000),
                    bar("2024-01-02", 11.0, 11.5, 10.5, 11.2, None),
                    bar("2024-01-03", None, 12.5, 11.5, 12.2, 3000),
                ]}

    def test_skips_bar_with_missing_ohlc(self):
        assert len(scdl.extract_rows(self._history())) == 2

    def test_date_is_naive_midnight_datetime(self):
        rows = scdl.extract_rows(self._history())
        assert rows[0]["date"] == dt.datetime(2024, 1, 1)

    def test_volume_none_safe(self):
        rows = scdl.extract_rows(self._history())
        assert rows[1]["volume"] is None
        assert rows[0]["volume"] == 1000


class TestMain:
    def test_invalid_start_date_exits_1(self, capsys):
        # No monkeypatching: build_params/parse_date rejects the date before
        # any network call, so this exercises the real error path.
        with pytest.raises(SystemExit) as exc:
            scdl.main(["AAA", "--start", "not-a-date"])
        assert exc.value.code == 1
        assert "invalid date" in capsys.readouterr().err
