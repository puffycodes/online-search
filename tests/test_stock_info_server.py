"""Tests for app/stock_information/stock_info_server: symbol validation, quote assembly, HTTP handler, arg parsing."""

import io
import json
import sys
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "app" / "stock_information"))

import stock_info_server as sis  # noqa: E402


class TestNormalizeSymbol:
    @pytest.mark.parametrize(
        "raw, expected",
        [("aapl", "AAPL"), ("  vod.l ", "VOD.L"), ("BRK-B", "BRK-B"), ("^gspc", "^GSPC"), ("EURUSD=X", "EURUSD=X")],
    )
    def test_accepts_yahoo_notation(self, raw, expected):
        assert sis.normalize_symbol(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", None, "a/b", "AA PL", "A" * 21, "<script>"])
    def test_rejects_invalid(self, raw):
        with pytest.raises(ValueError, match="invalid stock symbol"):
            sis.normalize_symbol(raw)


class TestGetStockInfo:
    def _patch(self, monkeypatch, result):
        calls = []

        def fake_fetch(symbol, params):
            calls.append((symbol, params))
            return result

        monkeypatch.setattr(sis.yf, "fetch_history", fake_fetch)
        return calls

    def test_uses_meta_fields_when_present(self, monkeypatch, chart_result):
        chart_result["meta"].update(
            {
                "longName": "Triple A Inc.",
                "regularMarketPrice": 12.34,
                "regularMarketTime": 1704283200,  # 2024-01-03 12:00 UTC
                "regularMarketDayHigh": 13.0,
                "regularMarketDayLow": 12.0,
                "fiftyTwoWeekLow": 9.5,
                "fiftyTwoWeekHigh": 15.25,
                "timezone": "UTC",
            }
        )
        calls = self._patch(monkeypatch, chart_result)
        info = sis.get_stock_info("AAA")
        assert calls[0][0] == "AAA"
        assert calls[0][1]["range"] == sis.QUOTE_RANGE
        assert info == {
            "name": "Triple A Inc.",
            "symbol": "AAA",
            "exchange": "TestExchange",
            "currency": "USD",
            "price": 12.34,
            "price_time": "2024-01-03 12:00 UTC",
            "session_date": "2024-01-03",
            "session_high": 13.0,
            "session_low": 12.0,
            "previous_close": 11.2,
            "change": 1.14,
            "change_pct": pytest.approx(1.14 / 11.2),
            "week52_low": 9.5,
            "week52_high": 15.25,
        }

    def test_session_date_honours_gmtoffset(self, monkeypatch, chart_result):
        chart_result["meta"].update(
            {
                "gmtoffset": 8 * 3600,
                "regularMarketPrice": 1.0,
                "regularMarketTime": 1704283200 + 12 * 3600,  # 2024-01-04 00:00 UTC
                "regularMarketDayHigh": 2.0,
                "regularMarketDayLow": 0.5,
            }
        )
        self._patch(monkeypatch, chart_result)
        info = sis.get_stock_info("AAA")
        assert info["session_date"] == "2024-01-04"
        assert info["price_time"] == "2024-01-04 08:00"

    def test_falls_back_to_latest_bar(self, monkeypatch, chart_result):
        chart_result["meta"]["shortName"] = "Triple A"
        self._patch(monkeypatch, chart_result)
        info = sis.get_stock_info("AAA")
        assert info["name"] == "Triple A"
        assert info["price"] == 12.2
        assert info["price_time"] is None
        assert info["session_date"] == "2024-01-03"
        assert (info["session_high"], info["session_low"]) == (12.5, 11.5)
        assert info["previous_close"] == 11.2
        assert info["change"] == 1.0
        assert info["change_pct"] == pytest.approx(1.0 / 11.2)
        assert (info["week52_low"], info["week52_high"]) == (None, None)

    def test_change_ignores_in_progress_bar_that_has_a_close(self, monkeypatch, chart_result):
        # The latest session's own bar (2024-01-03) already carries a close;
        # movement must be measured against 2024-01-02, not that bar.
        chart_result["meta"].update(
            {
                "regularMarketPrice": 12.2,
                "regularMarketTime": 1704283200,
                "regularMarketDayHigh": 12.5,
                "regularMarketDayLow": 11.5,
            }
        )
        self._patch(monkeypatch, chart_result)
        info = sis.get_stock_info("AAA")
        assert info["previous_close"] == 11.2
        assert info["change"] == 1.0

    def test_no_earlier_bar_leaves_change_empty(self, monkeypatch, chart_result):
        chart_result["timestamp"] = chart_result["timestamp"][-1:]
        quote = chart_result["indicators"]["quote"][0]
        for key in quote:
            quote[key] = quote[key][-1:]
        chart_result["indicators"]["adjclose"][0]["adjclose"] = [12.1]
        self._patch(monkeypatch, chart_result)
        info = sis.get_stock_info("AAA")
        assert (info["previous_close"], info["change"], info["change_pct"]) == (None, None, None)

    def test_name_falls_back_to_symbol(self, monkeypatch, chart_result):
        self._patch(monkeypatch, chart_result)
        assert sis.get_stock_info("AAA")["name"] == "AAA"

    def test_no_price_raises(self, monkeypatch, chart_result):
        chart_result["indicators"]["quote"][0]["close"] = [None, None, None]
        self._patch(monkeypatch, chart_result)
        with pytest.raises(requests.RequestException, match="no price data"):
            sis.get_stock_info("AAA")


def _fundamentals(price=100.0):
    """A neutral stock_data.fundamentals_view() with enough for every valuation method."""
    return {
        "source": "Test", "notes": [],
        "name": "Triple A Inc.", "exchange": "TST", "currency": "USD",
        "sector": "Technology", "industry": "Consumer Electronics",
        "price": price, "market_cap": None, "shares_outstanding": 1e9,
        "free_cash_flow": 5e9, "operating_cash_flow": None, "ebitda": 8e9, "revenue": 40e9,
        "net_income": None, "total_debt": 2e9, "total_cash": 1e9,
        "eps_ttm": 5.0, "eps_forward": None, "book_value_per_share": None, "beta": 1.0,
        "trailing_pe": 20.0, "forward_pe": None, "price_to_sales": 2.5, "price_to_book": None,
        "enterprise_value": 101e9, "ev_to_ebitda": 12.0,
        "gross_margin": None, "operating_margin": None, "net_margin": None,
        "return_on_equity": None, "return_on_assets": None,
        "revenue_growth": None, "earnings_growth": None,
        "debt_to_equity": None, "current_ratio": None, "quick_ratio": None,
        "dividend_per_share": 0.02 * price, "payout_ratio": None,
        "analyst_growth_1y": None, "analyst_growth_5y": None,
    }


class TestGetValuation:
    def test_runs_intrinsic_value_pipeline_with_defaults(self, monkeypatch):
        seen = []
        monkeypatch.setattr(sis.stock_data, "fundamentals_view",
                            lambda s: seen.append(s) or _fundamentals())
        out = sis.get_valuation("AAA")
        assert seen == ["AAA"]
        assert out["symbol"] == "AAA" and out["price"] == 100.0
        assert (out["sector"], out["industry"]) == ("Technology", "Consumer Electronics")
        assert "industry" not in out["inputs"]
        assert out["inputs"]["trailing_pe"] == 20.0  # read by the page's P/E line
        assert out["inputs"]["dividend_rate"] == 2.0  # 2% yield x 100.0; page shows 2.0 / 100.0 = 2.00%
        # CAPM default: 4% + 1.0 x 5%
        assert out["assumptions"]["discount_rate"] == pytest.approx(0.09)
        est = out["estimates"]
        assert set(est) == {
            "dcf_two_stage", "reverse_dcf_implied_growth", "dividend_discount", "pe_multiple",
            "graham", "ev_ebitda_multiple", "ps_multiple", "ev_reported_to_equity",
        }
        assert est["pe_multiple"]["value_per_share"] == pytest.approx(100.0)  # 5 EPS x 20 P/E
        assert est["dcf_two_stage"]["value_per_share"] > 0
        summary = out["summary"]
        assert summary == sis.summarize_estimates(out)
        counted = summary["undervalued"] + summary["fair_value"] + summary["overvalued"]
        assert counted + summary["not_available"] == len(
            sis.VALUATION_METHODS
        )
        assert out["indicators"]["trailing_pe"] == 20.0  # read by the page's Fundamentals section
        json.dumps(out)  # must be serializable for the HTTP response

    def test_no_price_raises(self, monkeypatch):
        view = {**_fundamentals(), "price": None}
        monkeypatch.setattr(sis.stock_data, "fundamentals_view", lambda s: view)
        with pytest.raises(ValueError, match="no usable fundamentals"):
            sis.get_valuation("AAA")


def _payload(price, values):
    """A build_json()-shaped payload with ``values`` mapped onto VALUATION_METHODS in order."""
    estimates = {m: {"value_per_share": None} for m in sis.VALUATION_METHODS}
    for method, value in zip(sis.VALUATION_METHODS, values):
        estimates[method]["value_per_share"] = value
    estimates["reverse_dcf_implied_growth"] = {"implied_growth": 0.05}
    return {"price": price, "estimates": estimates}


class TestSummarizeEstimates:
    def test_counts_undervalued_fair_overvalued(self):
        out = sis.summarize_estimates(_payload(100.0, [80.0, 99.5, 100.0, 100.9, 150.0, 101.0, None]))
        # Estimates above the price -> undervalued, below -> overvalued.
        # 99.5 / 100.0 / 100.9 are within 1%; 101.0 is exactly 1% away, so undervalued.
        assert out == {
            "undervalued": 2, "fair_value": 3, "overvalued": 1, "not_available": 1, "threshold": 0.01,
        }

    def test_negative_value_counts_as_overvalued(self):
        out = sis.summarize_estimates(_payload(100.0, [-20.0]))
        assert (out["overvalued"], out["not_available"]) == (1, len(sis.VALUATION_METHODS) - 1)

    def test_reverse_dcf_is_not_counted(self):
        out = sis.summarize_estimates(_payload(100.0, []))
        assert out["not_available"] == len(sis.VALUATION_METHODS)
        assert "reverse_dcf_implied_growth" not in sis.VALUATION_METHODS

    def test_custom_threshold(self):
        out = sis.summarize_estimates(_payload(100.0, [96.0, 104.0]), threshold=0.05)
        assert out["fair_value"] == 2 and out["threshold"] == 0.05


class _Handler(sis.StockInfoHandler):
    """Drives do_GET without a socket: captures status, headers, and body."""

    def __init__(self, path):
        self.path = path
        self.wfile = io.BytesIO()
        self.status = None
        self.headers_out = {}

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, key, value):
        self.headers_out[key] = value

    def end_headers(self):
        pass


def _get(path):
    handler = _Handler(path)
    handler.do_GET()
    return handler


class TestHandler:
    def test_serves_page(self):
        h = _get("/")
        assert h.status == 200
        assert h.headers_out["Content-Type"].startswith("text/html")
        body = h.wfile.getvalue().decode()
        assert 'id="symbol-input"' in body and 'id="submit-btn"' in body

    def test_quote_success(self, monkeypatch):
        seen = []
        monkeypatch.setattr(sis, "get_stock_info", lambda s: seen.append(s) or {"symbol": s})
        h = _get("/api/quote?symbol=%20aapl")
        assert h.status == 200
        assert seen == ["AAPL"]
        assert json.loads(h.wfile.getvalue()) == {"symbol": "AAPL"}

    def test_quote_invalid_symbol_is_400(self, monkeypatch):
        monkeypatch.setattr(sis, "get_stock_info", lambda s: pytest.fail("should not fetch"))
        h = _get("/api/quote?symbol=a/b")
        assert h.status == 400
        assert "invalid stock symbol" in json.loads(h.wfile.getvalue())["error"]

    def test_quote_missing_symbol_is_400(self):
        assert _get("/api/quote").status == 400

    def test_quote_fetch_error_is_502(self, monkeypatch):
        def boom(symbol):
            raise requests.RequestException("No data found")

        monkeypatch.setattr(sis, "get_stock_info", boom)
        h = _get("/api/quote?symbol=ZZZ")
        assert h.status == 502
        assert json.loads(h.wfile.getvalue())["error"] == "failed to fetch quote for 'ZZZ': No data found"

    def test_valuation_success(self, monkeypatch):
        monkeypatch.setattr(sis, "get_valuation", lambda s: {"symbol": s, "estimates": {}})
        h = _get("/api/valuation?symbol=aapl")
        assert h.status == 200
        assert json.loads(h.wfile.getvalue()) == {"symbol": "AAPL", "estimates": {}}

    def test_valuation_invalid_symbol_is_400(self, monkeypatch):
        monkeypatch.setattr(sis, "get_valuation", lambda s: pytest.fail("should not fetch"))
        assert _get("/api/valuation?symbol=a/b").status == 400

    def test_valuation_fetch_error_is_502(self, monkeypatch):
        def boom(symbol):
            raise ValueError("no usable fundamentals returned")

        monkeypatch.setattr(sis, "get_valuation", boom)
        h = _get("/api/valuation?symbol=ZZZ")
        assert h.status == 502
        assert json.loads(h.wfile.getvalue())["error"] == (
            "failed to fetch valuation for 'ZZZ': no usable fundamentals returned"
        )

    def test_page_has_valuation_section(self):
        body = _get("/").wfile.getvalue().decode()
        assert 'id="valuation-rows"' in body and "/api/valuation" in body
        for section_id in ("company-name", "company-symbol", "company-sector", "company-industry",
                           "company-market-cap", "company-pe", "company-dividend-yield", "week52-low", "week52-high", "week52-marker",
                           "day-marker", "count-undervalued", "count-fair-value", "count-overvalued",
                           "current-price", "price-change", "session-high", "session-low",
                           "previous-close", "fundamentals-status", "indicator-rows"):
            assert f'id="{section_id}"' in body

    def test_unknown_path_is_404(self):
        assert _get("/nope").status == 404


class TestParseArgs:
    def test_defaults(self):
        args = sis.parse_args([])
        assert (args.host, args.port) == (sis.DEFAULT_HOST, sis.DEFAULT_PORT)

    def test_overrides(self):
        args = sis.parse_args(["--host", "0.0.0.0", "--port", "9000"])
        assert (args.host, args.port) == ("0.0.0.0", 9000)

    def test_bad_port_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            sis.parse_args(["--port", "abc"])
        assert exc.value.code == 2
