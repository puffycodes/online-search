"""Tests for stock_rebased_chart: fetch_closes and main() base-date / skip / exit logic."""

import datetime as dt

import pytest
import requests

import stock_rebased_chart as src
import price_source
import yahoo_finance as yf


class TestFetchCloses:
    def test_skips_none_closes_and_returns_date_pairs(self, monkeypatch):
        result = {
            "meta": {"gmtoffset": 0},
            "timestamp": [1704067200, 1704153600, 1704240000],
            "indicators": {"quote": [{"close": [10.0, None, 12.0]}]},
        }
        monkeypatch.setattr(price_source, "fetch_history", lambda sym, params: result)
        _, rows = src.fetch_closes("AAA", {})
        assert rows == [(dt.date(2024, 1, 1), 10.0), (dt.date(2024, 1, 3), 12.0)]


class TestMain:
    @pytest.fixture(autouse=True)
    def _capture_render(self, monkeypatch):
        calls = {}

        def fake_render(series, base_date, out_path, show, benchmark=None):
            calls["series"] = series
            calls["base_date"] = base_date
            calls["benchmark"] = benchmark

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


class TestBenchmark:
    DATA = {
        "AAA": [(dt.date(2024, 1, 2), 100.0), (dt.date(2024, 1, 3), 110.0)],
        "^IDX": [(dt.date(2024, 1, 1), 40.0), (dt.date(2024, 1, 2), 50.0),
                 (dt.date(2024, 1, 3), 55.0)],
    }

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        calls = {}

        def fake_render(series, base_date, out_path, show, benchmark=None):
            calls.update(series=series, base_date=base_date, benchmark=benchmark)

        fetched = []

        def fetch(sym, params):
            fetched.append(sym)
            if sym not in self.DATA:
                raise requests.RequestException("nope")
            return ({}, list(self.DATA[sym]))

        monkeypatch.setattr(src, "render_chart", fake_render)
        monkeypatch.setattr(src, "fetch_closes", fetch)
        self.calls, self.fetched = calls, fetched

    def test_benchmark_rebased_and_passed_separately(self):
        src.main(["AAA", "--benchmark", "^IDX"])
        assert [name for name, _, _ in self.calls["series"]] == ["AAA"]
        name, dates, values = self.calls["benchmark"]
        assert name == "^IDX"
        assert dates[0] == dt.date(2024, 1, 1)
        assert values[1:] == [100.0, pytest.approx(110.0)]

    def test_benchmark_does_not_set_default_base_date(self):
        # The benchmark starts a day earlier; the base still comes from AAA.
        src.main(["AAA", "--benchmark", "^IDX"])
        assert self.calls["base_date"] == dt.date(2024, 1, 2)

    def test_no_benchmark_by_default(self):
        src.main(["AAA"])
        assert self.calls["benchmark"] is None
        assert self.fetched == ["AAA"]

    def test_failed_benchmark_still_draws_chart(self, capsys):
        src.main(["AAA", "--benchmark", "^NOPE"])
        assert self.calls["benchmark"] is None
        assert [name for name, _, _ in self.calls["series"]] == ["AAA"]
        assert "failed to fetch prices for '^NOPE'" in capsys.readouterr().err

    def test_benchmark_without_base_date_close_is_dropped(self, capsys):
        # ^GAP was closed on AAA's first date (2024-01-02), e.g. a holiday.
        self.DATA = {**self.DATA, "^GAP": [(dt.date(2024, 1, 3), 7.0)]}
        src.main(["AAA", "--benchmark", "^GAP"])
        assert self.calls["benchmark"] is None
        assert [name for name, _, _ in self.calls["series"]] == ["AAA"]
        assert "'^GAP' has no settled close on 2024-01-02" in capsys.readouterr().err

    def test_benchmark_listed_as_symbol_is_drawn_once(self):
        src.main(["AAA", "^idx", "--benchmark", "^IDX"])
        assert [name for name, _, _ in self.calls["series"]] == ["AAA"]
        assert self.calls["benchmark"][0] == "^IDX"
        assert self.fetched == ["AAA", "^IDX"]

    def test_only_the_benchmark_exits_2(self, capsys):
        with pytest.raises(SystemExit) as exc:
            src.main(["^IDX", "--benchmark", "^IDX"])
        assert exc.value.code == 2
        assert "at least one symbol besides the --benchmark" in capsys.readouterr().err
        assert self.fetched == []

    def test_benchmark_alone_with_data_is_not_enough(self, capsys):
        with pytest.raises(SystemExit) as exc:
            src.main(["ZZZ", "--benchmark", "^IDX"])
        assert exc.value.code == 1
        assert "no price data found for any symbol" in capsys.readouterr().err


class TestRenderChart:
    def test_benchmark_line_is_dashed_and_labelled(self, tmp_path, monkeypatch):
        pytest.importorskip("matplotlib")
        import matplotlib.pyplot as plt

        lines = {}
        real_close = plt.close

        def grab(fig):
            for line in fig.axes[0].get_lines():
                lines[line.get_label()] = line
            real_close(fig)

        monkeypatch.setattr(plt, "close", grab)
        dates = [dt.date(2024, 1, 1), dt.date(2024, 1, 2)]
        out = tmp_path / "chart.png"
        src.render_chart([("AAA", dates, [100.0, 110.0])], dates[0], str(out), False,
                         benchmark=("^IDX", dates, [100.0, 105.0]))
        assert out.exists()
        bench = lines["^IDX (benchmark)"]
        assert bench.get_linestyle() == "--"
        assert bench.get_color() == src.BENCHMARK_COLOR
        assert lines["AAA"].get_linestyle() == "-"
