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

    def test_name_falls_back_to_symbol(self, monkeypatch, chart_result):
        self._patch(monkeypatch, chart_result)
        assert sis.get_stock_info("AAA")["name"] == "AAA"

    def test_no_price_raises(self, monkeypatch, chart_result):
        chart_result["indicators"]["quote"][0]["close"] = [None, None, None]
        self._patch(monkeypatch, chart_result)
        with pytest.raises(requests.RequestException, match="no price data"):
            sis.get_stock_info("AAA")


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
