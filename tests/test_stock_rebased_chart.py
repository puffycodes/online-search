"""Tests for stock_rebased_chart: fetch_closes and main() base-date / skip / exit logic."""

import datetime as dt

import pytest
import requests

import stock_rebased_chart as src
import yahoo_finance as yf


class TestFetchCloses:
    def test_skips_none_closes_and_returns_date_pairs(self, monkeypatch):
        result = {
            "meta": {"gmtoffset": 0},
            "timestamp": [1704067200, 1704153600, 1704240000],
            "indicators": {"quote": [{"close": [10.0, None, 12.0]}]},
        }
        monkeypatch.setattr(yf, "fetch_history", lambda sym, params: result)
        _, rows = src.fetch_closes("AAA", {})
        assert rows == [(dt.date(2024, 1, 1), 10.0), (dt.date(2024, 1, 3), 12.0)]


class TestMain:
    @pytest.fixture(autouse=True)
    def _capture_render(self, monkeypatch):
        calls = {}

        def fake_render(series, base_date, out_path, show):
            calls["series"] = series
            calls["base_date"] = base_date

        monkeypatch.setattr(src, "render_chart", fake_render)
        self.render_calls = calls

    def test_all_symbols_fail_exits(self, monkeypatch, capsys):
        def boom(sym, params):
            raise requests.RequestException("nope")

        monkeypatch.setattr(src, "fetch_closes", boom)
        with pytest.raises(SystemExit):
            src.main(["AAA", "BBB"])
        assert "no price data found for any symbol" in capsys.readouterr().err

    def test_default_base_date_is_first_symbol_first_date(self, monkeypatch):
        data = {
            "AAA": [(dt.date(2024, 1, 1), 100.0), (dt.date(2024, 1, 2), 110.0)],
            "BBB": [(dt.date(2024, 1, 1), 50.0), (dt.date(2024, 1, 2), 40.0)],
        }
        monkeypatch.setattr(src, "fetch_closes", lambda sym, params: ({}, list(data[sym])))
        src.main(["AAA", "BBB"])
        assert self.render_calls["base_date"] == dt.date(2024, 1, 1)
        series = {name: values for name, _, values in self.render_calls["series"]}
        assert series["AAA"][0] == 100.0
        assert series["BBB"][1] == pytest.approx(80.0)

    def test_base_date_falls_back_when_first_symbol_missing(self, monkeypatch):
        def fetch(sym, params):
            if sym == "AAA":
                raise requests.RequestException("nope")
            return ({}, [(dt.date(2024, 2, 1), 10.0), (dt.date(2024, 2, 2), 20.0)])

        monkeypatch.setattr(src, "fetch_closes", fetch)
        src.main(["AAA", "BBB"])
        assert self.render_calls["base_date"] == dt.date(2024, 2, 1)

    def test_symbol_without_base_date_close_is_skipped(self, monkeypatch, capsys):
        def fetch(sym, params):
            if sym == "AAA":
                return ({}, [(dt.date(2024, 1, 1), 100.0), (dt.date(2024, 1, 2), 110.0)])
            return ({}, [(dt.date(2024, 1, 2), 50.0)])  # no close on 2024-01-01

        monkeypatch.setattr(src, "fetch_closes", fetch)
        src.main(["AAA", "BBB"])
        assert [name for name, _, _ in self.render_calls["series"]] == ["AAA"]
        assert "no settled close" in capsys.readouterr().err

    def test_invalid_base_date_exits(self, capsys):
        with pytest.raises(SystemExit):
            src.main(["AAA", "--base-date", "not-a-date"])
        assert "invalid date" in capsys.readouterr().err

    def test_last_zero_rejected_at_parse_time(self):
        with pytest.raises(SystemExit) as exc:
            src.main(["AAA", "--last", "0"])
        assert exc.value.code == 2
