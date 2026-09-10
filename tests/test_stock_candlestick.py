"""Tests for stock_candlestick: the --ma / --flip-ma arg parsers and extract_rows."""

import argparse
import datetime as dt

import pytest

import stock_candlestick as scdl


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
    def _result(self):
        return {
            "meta": {"symbol": "AAA", "gmtoffset": 0},
            "timestamp": [1704067200, 1704153600, 1704240000],
            "indicators": {
                "quote": [{
                    "open": [10.0, 11.0, None],
                    "high": [10.5, 11.5, 12.5],
                    "low": [9.5, 10.5, 11.5],
                    "close": [10.2, 11.2, 12.2],
                    "volume": [1000, None, 3000],
                }],
            },
        }

    def test_skips_bar_with_missing_ohlc(self):
        _, rows = scdl.extract_rows(self._result())
        assert len(rows) == 2

    def test_date_is_datetime(self):
        _, rows = scdl.extract_rows(self._result())
        assert isinstance(rows[0]["date"], dt.datetime)

    def test_volume_none_safe(self):
        _, rows = scdl.extract_rows(self._result())
        assert rows[1]["volume"] is None
        assert rows[0]["volume"] == 1000
