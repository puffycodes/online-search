"""Tests for daily_prices: window flags and resolution, row shaping, windowing, the text table."""

import argparse
import datetime as dt

import pytest

import daily_prices as dp

TODAY = dt.date(2026, 10, 21)


def _row(date, close=1.0, adj=None):
    return {"date": date, "open": 1.0, "high": 1.0, "low": 1.0, "close": close,
            "adj_close": adj, "volume": 10}


class TestParseDate:
    def test_valid(self):
        assert dp.parse_date("2026-01-02") == dt.date(2026, 1, 2)

    def test_invalid(self):
        with pytest.raises(ValueError, match="invalid date"):
            dp.parse_date("02/01/2026")


class TestAddWindowArgs:
    def _parser(self):
        parser = argparse.ArgumentParser()
        dp.add_window_args(parser, "help")
        return parser

    def test_defaults_none(self):
        args = self._parser().parse_args([])
        assert (args.start, args.end, args.last) == (None, None, None)

    def test_last_zero_rejected(self):
        with pytest.raises(SystemExit) as exc:
            self._parser().parse_args(["--last", "0"])
        assert exc.value.code == 2


class TestResolveWindow:
    def test_default_days(self):
        assert dp.resolve_window(today=TODAY) == (TODAY - dt.timedelta(days=dp.DEFAULT_DAYS), TODAY)

    def test_last_looks_back_generously(self):
        assert dp.resolve_window(last=5, today=TODAY) == (TODAY - dt.timedelta(days=20), TODAY)

    def test_start_defaults_end_to_today(self):
        assert dp.resolve_window(start="2026-10-01", today=TODAY) == (dt.date(2026, 10, 1), TODAY)

    def test_start_beats_last(self):
        first, final = dp.resolve_window(start="2026-01-01", end="2026-02-01", last=3, today=TODAY)
        assert (first, final) == (dt.date(2026, 1, 1), dt.date(2026, 2, 1))

    def test_single_day_allowed(self):
        assert dp.resolve_window(start="2026-10-01", end="2026-10-01")[0] == dt.date(2026, 10, 1)

    def test_end_without_start(self):
        with pytest.raises(ValueError, match="--end requires --start"):
            dp.resolve_window(end="2026-10-01", today=TODAY)

    def test_end_before_start(self):
        with pytest.raises(ValueError, match="before start"):
            dp.resolve_window(start="2026-10-02", end="2026-10-01")

    def test_bad_date(self):
        with pytest.raises(ValueError, match="invalid date"):
            dp.resolve_window(start="nope")


class TestPriceRow:
    def test_rounds_and_converts_strings(self):
        row = dp.price_row("2026-10-20", "10.123456", 11, "9.5", "10.25", None, "1234")
        assert row == {"date": "2026-10-20", "open": 10.1235, "high": 11.0, "low": 9.5,
                       "close": 10.25, "adj_close": None, "volume": 1234}
        assert isinstance(row["volume"], int)

    def test_missing_values_none(self):
        row = dp.price_row("2026-10-20", None, "", None, 1, None, None)
        assert row["open"] is None and row["high"] is None and row["volume"] is None


class TestInWindow:
    def test_inclusive_bounds(self):
        rows = [_row("2026-10-01"), _row("2026-10-02"), _row("2026-10-03")]
        kept = dp.in_window(rows, dt.date(2026, 10, 2), dt.date(2026, 10, 3))
        assert [r["date"] for r in kept] == ["2026-10-02", "2026-10-03"]


class TestPrintTable:
    def test_header_rows_and_summary(self, capsys):
        dp.print_table("AAA - Test", [_row("2026-10-01"), _row("2026-10-02", close=2.0)], "USD")
        out = capsys.readouterr().out
        assert "AAA - Test - 2 session(s)" in out
        assert "Adj Close" not in out
        assert "Most recent session (2026-10-02)" in out
        assert out.rstrip().endswith("C 2.0000 USD")

    def test_adj_close_column_when_differs(self, capsys):
        dp.print_table("AAA", [_row("2026-10-01", close=1.0, adj=0.9)])
        assert "Adj Close" in capsys.readouterr().out

    def test_no_currency_suffix(self, capsys):
        dp.print_table("AAA", [_row("2026-10-01")])
        assert capsys.readouterr().out.rstrip().endswith("C 1.0000")
