"""Tests for market_top_volume: output records, formatting, arguments, main().

The Yahoo screeners behind stock_data.top_movers() (market and metric
tables, the volume floor, sorting, the crumb) are tested in
test_yahoo_finance.py; here every row is already in stock_data's neutral shape.
"""

import json

import pytest
import requests

import market_top_volume as mtv
import stock_data


def _row(symbol="AAA", name="Alpha", exchange="NYSE", volume=123, price=10.5,
         change_percent=1.25, currency="USD"):
    return {"symbol": symbol, "name": name, "exchange": exchange, "volume": volume,
            "price": price, "change_percent": change_percent, "currency": currency}


def _movers(*rows):
    return {"source": "Test", "notes": [], "movers": list(rows)}


class TestQuoteToDict:
    def test_defaults_for_empty_row(self):
        empty = dict.fromkeys(_row())
        assert mtv.quote_to_dict(1, empty) == {
            "rank": 1, "symbol": "?", "name": "(unknown)", "exchange": "?",
            "volume": 0, "price": 0, "change_percent": 0, "currency": "",
        }

    def test_maps_fields(self):
        assert mtv.quote_to_dict(3, _row()) == {
            "rank": 3, "symbol": "AAA", "name": "Alpha", "exchange": "NYSE", "volume": 123,
            "price": 10.5, "change_percent": 1.25, "currency": "USD",
        }

    def test_metric_labels_cover_metrics(self):
        assert set(mtv.METRIC_LABELS) == set(stock_data.MOVER_METRICS)


class TestFormatQuote:
    ROW = {"rank": 1, "symbol": "A", "name": "Alpha", "exchange": "NYSE",
           "volume": 100, "price": 5, "change_percent": 1.0, "currency": "USD"}

    def test_volume_metric_leads_with_volume(self):
        stats_line = mtv.format_quote(self.ROW, "volume").splitlines()[1]
        assert stats_line.index("Volume") < stats_line.index("Change")

    def test_mover_metric_leads_with_change(self):
        stats_line = mtv.format_quote(self.ROW, "gainers").splitlines()[1]
        assert stats_line.index("Change") < stats_line.index("Volume")


class TestParseArgs:
    def test_defaults(self):
        args = mtv.parse_args([])
        assert (args.market, args.metric, args.limit, args.json) == ("us", "volume", 10, False)

    def test_markets_come_from_the_provider(self, monkeypatch):
        monkeypatch.setitem(stock_data.PROVIDERS, "mover_markets", lambda: ["mars", "us"])
        assert mtv.parse_args(["--market", "mars"]).market == "mars"
        with pytest.raises(SystemExit) as exc:
            mtv.parse_args(["--market", "uk"])
        assert exc.value.code == 2

    def test_unknown_metric_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            mtv.parse_args(["--metric", "momentum"])
        assert exc.value.code == 2


class TestMain:
    @pytest.mark.parametrize("bad", ["0", "-1", "abc"])
    def test_invalid_limit_exits_2_before_fetch(self, monkeypatch, bad):
        def fail(*a, **k):
            raise AssertionError("should not fetch")

        monkeypatch.setattr(stock_data, "top_movers", fail)
        with pytest.raises(SystemExit) as exc:
            mtv.main(["--limit", bad, "--json"])
        assert exc.value.code == 2

    def test_arguments_passed_through(self, monkeypatch, capsys):
        seen = []
        monkeypatch.setattr(stock_data, "top_movers",
                            lambda market, metric, limit: seen.append((market, metric, limit))
                            or _movers())
        mtv.main(["--market", "uk", "--metric", "losers", "--limit", "3", "--json"])
        assert seen == [("uk", "losers", 3)]
        assert json.loads(capsys.readouterr().out) == []

    def test_json_rows_ranked_without_source(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "top_movers",
                            lambda *a: _movers(_row("AAA"), _row("BBB", name=None)))
        mtv.main(["--json"])
        out = json.loads(capsys.readouterr().out)
        assert [(r["rank"], r["symbol"], r["name"]) for r in out] == [
            (1, "AAA", "Alpha"), (2, "BBB", "(unknown)")]
        assert "source" not in out[0]

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "top_movers", lambda *a: _movers(_row()))
        mtv.main(["--market", "nyse"])
        out = capsys.readouterr().out
        assert out.startswith("Top 1 stock(s) by volume on NYSE:")
        assert "1. AAA - Alpha (NYSE)" in out

    def test_no_rows(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "top_movers", lambda *a: _movers())
        mtv.main(["--metric", "gainers"])
        assert "No gainers data returned for market 'us'." in capsys.readouterr().out

    def test_error_exits_json(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise requests.RequestException("screener down")

        monkeypatch.setattr(stock_data, "top_movers", boom)
        with pytest.raises(SystemExit) as exc:
            mtv.main(["--json"])
        assert exc.value.code == 1
        assert "screener down" in json.loads(capsys.readouterr().err)["error"]
