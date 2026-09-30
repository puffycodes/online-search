#!/usr/bin/env python3
"""
Serve a small local web page for looking up a single stock.

The page has a text box for a ticker (Yahoo notation: AAPL, VOD.L,
D05.SI, ...) and a submit button. On submit, the browser calls this
server's /api/quote endpoint, which fetches the quote through the same
Yahoo Finance chart helpers as stock_close_history.py (yahoo_finance.py
at the repository root) and returns the company name, symbol, current
price, and the high/low of the latest session with its date.

A server is needed (rather than a static page) because Yahoo's endpoints
don't send CORS headers, so a browser can't call them directly.

Usage:
    python3 stock_info_server.py [--host HOST] [--port PORT]
"""

import argparse
import datetime as dt
import json
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# yahoo_finance.py and stock_close_history.py live at the repository root,
# two levels up from this file (app/stock_information/stock_info_server.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402

import yahoo_finance as yf  # noqa: E402
from stock_close_history import extract_rows  # noqa: E402

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
# A few days of daily bars is enough to find the latest session even
# across weekends/holidays.
QUOTE_RANGE = "5d"
# Yahoo tickers: letters, digits and . - ^ = (e.g. VOD.L, BRK-B, ^GSPC, EURUSD=X).
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9.^=\-]{1,20}$")

PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stock Information</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f5f7fa;
    --card-bg: #ffffff;
    --text: #1a1a1a;
    --muted: #6b6b6b;
    --accent: #1f6feb;
    --border: #e1e4e8;
    --error: #c62828;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #121212;
      --card-bg: #1c1c1c;
      --text: #eaeaea;
      --muted: #9a9a9a;
      --border: #2c2c2c;
      --error: #ef9a9a;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }
  header {
    background: var(--accent);
    padding: 1.5rem 1rem;
    text-align: center;
    color: #fff;
  }
  header h1 { margin: 0; font-size: 1.6rem; }
  header p { margin: 0.35rem 0 0; font-size: 0.85rem; opacity: 0.9; }
  main {
    max-width: 560px;
    margin: 0 auto;
    padding: 1.25rem 1rem 3rem;
  }
  form { display: flex; gap: 0.5rem; }
  #symbol-input {
    flex: 1;
    min-width: 0;
    padding: 0.55rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--card-bg);
    color: var(--text);
    font-size: 1rem;
    text-transform: uppercase;
  }
  #submit-btn {
    padding: 0.55rem 1.2rem;
    border: none;
    border-radius: 6px;
    background: var(--accent);
    color: #fff;
    font-size: 1rem;
    cursor: pointer;
  }
  #submit-btn:disabled { opacity: 0.6; cursor: default; }
  #status { min-height: 1.2em; margin: 0.75rem 0; color: var(--muted); font-size: 0.9rem; }
  #status.error { color: var(--error); }
  .card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.1rem 1.25rem;
  }
  .card h2 { margin: 0; font-size: 1.3rem; }
  .card .symbol { color: var(--muted); font-size: 0.9rem; margin-top: 0.2rem; }
  .price { font-size: 2rem; font-weight: 600; margin: 0.9rem 0 0.2rem; }
  .price-label { color: var(--muted); font-size: 0.8rem; }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.35rem 1rem;
    margin: 1rem 0 0;
    padding-top: 0.9rem;
    border-top: 1px solid var(--border);
  }
  dt { color: var(--muted); }
  dd { margin: 0; font-variant-numeric: tabular-nums; }
  [hidden] { display: none !important; }
</style>
</head>
<body>
<header>
  <h1>Stock Information</h1>
  <p>Enter a ticker in Yahoo notation, e.g. AAPL, VOD.L, D05.SI</p>
</header>
<main>
  <form id="quote-form">
    <input id="symbol-input" name="symbol" type="text" placeholder="Stock symbol"
           autocomplete="off" spellcheck="false" required>
    <button id="submit-btn" type="submit">Submit</button>
  </form>
  <p id="status"></p>
  <section id="result" class="card" hidden>
    <h2 id="company-name"></h2>
    <div class="symbol" id="symbol-line"></div>
    <div class="price" id="current-price"></div>
    <div class="price-label" id="price-label"></div>
    <dl>
      <dt>Session date</dt><dd id="session-date"></dd>
      <dt>High</dt><dd id="session-high"></dd>
      <dt>Low</dt><dd id="session-low"></dd>
    </dl>
  </section>
</main>
<script>
(function () {
  var form = document.getElementById("quote-form");
  var input = document.getElementById("symbol-input");
  var button = document.getElementById("submit-btn");
  var status = document.getElementById("status");
  var result = document.getElementById("result");

  function setText(id, value) {
    document.getElementById(id).textContent = value;
  }

  function money(value, currency) {
    if (value === null || value === undefined) return "–";
    var text = Number(value).toLocaleString(undefined, {
      minimumFractionDigits: 2, maximumFractionDigits: 4
    });
    return currency ? text + " " + currency : text;
  }

  function render(q) {
    setText("company-name", q.name || q.symbol);
    setText("symbol-line", q.symbol + (q.exchange ? " · " + q.exchange : ""));
    setText("current-price", money(q.price, q.currency));
    setText("price-label", q.price_time ? "Current price as of " + q.price_time : "Current price");
    setText("session-date", q.session_date || "–");
    setText("session-high", money(q.session_high, q.currency));
    setText("session-low", money(q.session_low, q.currency));
    result.hidden = false;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var symbol = input.value.trim().toUpperCase();
    if (!symbol) return;

    button.disabled = true;
    status.className = "";
    status.textContent = "Looking up " + symbol + "…";

    fetch("/api/quote?symbol=" + encodeURIComponent(symbol))
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) throw new Error(body.error || ("HTTP " + response.status));
          return body;
        });
      })
      .then(function (q) {
        render(q);
        status.textContent = "";
      })
      .catch(function (err) {
        result.hidden = true;
        status.className = "error";
        status.textContent = "Lookup failed: " + err.message;
      })
      .finally(function () {
        button.disabled = false;
      });
  });
})();
</script>
</body>
</html>
"""


def normalize_symbol(value):
    """Return the upper-cased, stripped ticker, or raise ValueError if it isn't one."""
    symbol = (value or "").strip().upper()
    if not SYMBOL_PATTERN.match(symbol):
        raise ValueError(f"invalid stock symbol {value!r}")
    return symbol


def _local_time(timestamp, gmtoffset):
    return dt.datetime.utcfromtimestamp(timestamp + gmtoffset)


def get_stock_info(symbol):
    """Fetch the quote summary for ``symbol`` from Yahoo's chart endpoint.

    Returns a dict with name, symbol, exchange, currency, price,
    price_time, session_date, session_high, session_low. The price and
    session figures come from the chart ``meta`` block (which reflects
    an in-progress session); if Yahoo omits them, they fall back to the
    most recent settled daily bar. Raises requests.RequestException if
    Yahoo returns no usable price.
    """
    result = yf.fetch_history(symbol, yf.build_params(range_=QUOTE_RANGE))
    meta, rows = extract_rows(result)
    ticker, exchange, currency = yf.meta_summary(meta, symbol)
    gmtoffset = meta.get("gmtoffset", 0) or 0
    latest = rows[-1] if rows else {}

    price = meta.get("regularMarketPrice")
    if price is None:
        price = latest.get("close")
    if price is None:
        raise requests.RequestException("no price data returned for symbol")

    market_time = meta.get("regularMarketTime")
    high = meta.get("regularMarketDayHigh")
    low = meta.get("regularMarketDayLow")
    if market_time and high is not None and low is not None:
        session_date = _local_time(market_time, gmtoffset).strftime("%Y-%m-%d")
    else:
        session_date = latest.get("date")
        high = latest.get("high")
        low = latest.get("low")

    price_time = None
    if market_time:
        price_time = _local_time(market_time, gmtoffset).strftime("%Y-%m-%d %H:%M")
        if meta.get("timezone"):
            price_time += " " + meta["timezone"]

    return {
        "name": meta.get("longName") or meta.get("shortName") or ticker,
        "symbol": ticker,
        "exchange": exchange,
        "currency": currency,
        "price": price,
        "price_time": price_time,
        "session_date": session_date,
        "session_high": high,
        "session_low": low,
    }


class StockInfoHandler(BaseHTTPRequestHandler):
    """Serves the page at ``/`` and quote JSON at ``/api/quote?symbol=...``."""

    def _send(self, status, body, content_type):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status, payload):
        self._send(status, json.dumps(payload), "application/json; charset=utf-8")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._send(HTTPStatus.OK, PAGE_HTML, "text/html; charset=utf-8")
            return
        if url.path != "/api/quote":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        raw = parse_qs(url.query).get("symbol", [""])[0]
        try:
            symbol = normalize_symbol(raw)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        try:
            info = get_stock_info(symbol)
        except (requests.RequestException, ValueError, KeyError) as exc:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"error": f"failed to fetch quote for {symbol!r}: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, info)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Serve a local web page for looking up a stock's price."
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help=f"Interface to bind (default: {DEFAULT_HOST})"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Port to listen on (default: {DEFAULT_PORT})"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), StockInfoHandler)
    print(f"Serving Stock Information at http://{args.host}:{args.port}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
