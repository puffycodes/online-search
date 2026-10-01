#!/usr/bin/env python3
"""
Serve a small local web page for looking up a single stock.

The page has a text box for a ticker (Yahoo notation: AAPL, VOD.L,
D05.SI, ...) and a submit button. On submit, the browser calls this
server's /api/quote endpoint, which fetches the quote through the same
Yahoo Finance chart helpers as stock_close_history.py (yahoo_finance.py
at the repository root) and returns the company name, symbol, current
price, its movement since the previous close, the day low/high
of the latest session with its date, and the 52-week low/high (both
drawn as range bars with a marker at the current price).

The page then calls /api/valuation, which runs the same pipeline as
stock_intrinsic_value.py (Yahoo fundamentals -> every valuation.py
method, with that script's default assumptions) and shows how many
estimates sit below / about the same as / above the price, then each
estimate next to the price. The company's market cap, trailing P/E, dividend yield,
sector and industry come from the same fundamentals payload. It's a separate call because the fundamentals fetch
is slower and more fragile than the quote.

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

# yahoo_finance.py, stock_close_history.py and stock_intrinsic_value.py live
# at the repository root, two levels up from this file (app/stock_information/stock_info_server.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402

import stock_intrinsic_value as siv  # noqa: E402
import yahoo_finance as yf  # noqa: E402
from stock_close_history import extract_rows  # noqa: E402

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
# A few days of daily bars is enough to find the latest session even
# across weekends/holidays.
QUOTE_RANGE = "5d"
# Yahoo tickers: letters, digits and . - ^ = (e.g. VOD.L, BRK-B, ^GSPC, EURUSD=X).
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9.^=\-]{1,20}$")
# A valuation within this fraction of the price counts as "about the same".
SAME_THRESHOLD = 0.01
# The per-share estimates in stock_intrinsic_value.build_json() (everything
# but the reverse DCF, which is an implied growth rate, not a value).
VALUATION_METHODS = (
    "dcf_two_stage",
    "dividend_discount",
    "pe_multiple",
    "graham",
    "ev_ebitda_multiple",
    "ps_multiple",
    "ev_reported_to_equity",
)

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
    --up: #1a7f37;
    --down: #c62828;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #121212;
      --card-bg: #1c1c1c;
      --text: #eaeaea;
      --muted: #9a9a9a;
      --border: #2c2c2c;
      --error: #ef9a9a;
      --up: #56d364;
      --down: #f47067;
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
  .company-name { font-size: 1.35rem; font-weight: 600; margin: 0; }
  .company-symbol { color: var(--muted); margin: 0.15rem 0 0; }
  .inline-list { margin: 0.5rem 0 0; font-size: 0.9rem; }
  .inline-list > span + span::before { content: "·"; margin: 0 0.45rem; color: var(--muted); }
  .price-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.3rem 0.75rem; }
  .price { font-size: 2rem; font-weight: 600; }
  .change { font-weight: 600; font-variant-numeric: tabular-nums; }
  .change.up { color: var(--up); }
  .change.down { color: var(--down); }
  .price-label { color: var(--muted); font-size: 0.8rem; margin-top: 0.2rem; }
  .inline-list .label { color: var(--muted); }
  .inline-list .value { font-variant-numeric: tabular-nums; }
  h3 {
    margin: 1.25rem 0 0.6rem;
    padding-top: 0.9rem;
    border-top: 1px solid var(--border);
    font-size: 1.05rem;
  }
  h3:first-child { margin-top: 0; padding-top: 0; border-top: none; }
  #valuation-status { color: var(--muted); font-size: 0.9rem; margin: 0; }
  #valuation-status.error { color: var(--error); }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { padding: 0.4rem 0.3rem; border-bottom: 1px solid var(--border); text-align: right; }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--muted); font-weight: 500; }
  td { font-variant-numeric: tabular-nums; }
  .assumptions, .disclaimer { color: var(--muted); font-size: 0.8rem; margin: 0.6rem 0 0; }
  .range { margin: 0.75rem 0 0; font-size: 0.9rem; }
  .range-title { color: var(--muted); margin-bottom: 0.35rem; }
  .range-row { display: flex; align-items: center; gap: 0.6rem; }
  .range-row .value { white-space: nowrap; font-variant-numeric: tabular-nums; }
  .range-track {
    position: relative;
    flex: 1;
    min-width: 4rem;
    height: 6px;
    border-radius: 3px;
    background: var(--border);
  }
  .range-marker {
    position: absolute;
    top: 50%;
    width: 14px;
    height: 14px;
    margin-left: -7px;
    border-radius: 50%;
    background: var(--accent);
    border: 2px solid var(--card-bg);
    transform: translateY(-50%);
  }
  .range-caption { color: var(--muted); font-size: 0.8rem; margin-top: 0.35rem; }
  .prev-close { color: var(--muted); font-size: 0.9rem; }
  .prev-close .value { color: var(--text); font-variant-numeric: tabular-nums; }
  .stats { display: flex; gap: 0.5rem; margin: 0 0 0.75rem; }
  .stat {
    flex: 1;
    padding: 0.5rem 0.4rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    text-align: center;
  }
  .stat-count { display: block; font-size: 1.4rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .stat-label { color: var(--muted); font-size: 0.8rem; }
  .stats-note { color: var(--muted); font-size: 0.8rem; margin: -0.35rem 0 0.75rem; }
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
    <h3>Company</h3>
    <p class="company-name" id="company-name"></p>
    <p class="company-symbol" id="company-symbol"></p>
    <p class="inline-list">
      <span id="company-sector" title="Sector"></span><span id="company-industry" title="Industry"></span>
    </p>
    <p class="inline-list">
      <span id="company-market-cap" title="Market cap"></span><span id="company-pe" title="Trailing P/E"></span><span
        id="company-dividend-yield" title="Dividend yield"></span>
    </p>
    <h3>Price</h3>
    <div class="price-line">
      <span class="price" id="current-price"></span><span class="change" id="price-change"></span><span
        class="prev-close">Previous close <span class="value" id="previous-close"></span></span>
    </div>
    <div class="price-label" id="price-label"></div>
    <div class="range">
      <div class="range-title">Day range</div>
      <div class="range-row">
        <span class="value" id="session-low" title="Day low"></span>
        <div class="range-track" id="day-track">
          <div class="range-marker" id="day-marker" hidden></div>
        </div>
        <span class="value" id="session-high" title="Day high"></span>
      </div>
      <div class="range-caption" id="day-caption"></div>
    </div>
    <div class="range">
      <div class="range-title">52-week range</div>
      <div class="range-row">
        <span class="value" id="week52-low" title="52-week low"></span>
        <div class="range-track" id="week52-track">
          <div class="range-marker" id="week52-marker" hidden></div>
        </div>
        <span class="value" id="week52-high" title="52-week high"></span>
      </div>
      <div class="range-caption" id="week52-caption"></div>
    </div>
    <h3>Valuations</h3>
    <p id="valuation-status"></p>
    <div id="valuation" hidden>
      <div class="stats">
        <div class="stat"><span class="stat-count" id="count-below"></span><span
          class="stat-label">Below price</span></div>
        <div class="stat"><span class="stat-count" id="count-same"></span><span
          class="stat-label">About the same</span></div>
        <div class="stat"><span class="stat-count" id="count-above"></span><span
          class="stat-label">Above price</span></div>
      </div>
      <p class="stats-note" id="stats-note"></p>
      <table>
        <thead><tr><th>Method</th><th>Value / share</th><th>Price vs estimate</th></tr></thead>
        <tbody id="valuation-rows"></tbody>
      </table>
      <p class="assumptions" id="valuation-assumptions"></p>
      <p class="disclaimer">Mechanical estimates from Yahoo fundamentals and default
        assumptions (see stock_intrinsic_value.py) &mdash; not a forecast or investment advice.</p>
    </div>
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

  var valuationStatus = document.getElementById("valuation-status");
  var valuationBox = document.getElementById("valuation");
  var valuationRows = document.getElementById("valuation-rows");
  // Display order and labels for stock_intrinsic_value.build_json()'s estimates.
  var METHODS = [
    ["dcf_two_stage", "Two-stage DCF"],
    ["dividend_discount", "Dividend discount (Gordon)"],
    ["pe_multiple", "P/E multiple"],
    ["graham", "Graham formula"],
    ["ev_ebitda_multiple", "EV/EBITDA multiple"],
    ["ps_multiple", "P/S multiple"],
    ["ev_reported_to_equity", "Reported EV → equity (check)"]
  ];
  // Bumped per submit so a slow response for an older symbol is ignored.
  var requestId = 0;

  function bigMoney(value, currency) {
    if (value === null || value === undefined) return "–";
    var units = [["T", 1e12], ["B", 1e9], ["M", 1e6], ["K", 1e3]];
    var text = Number(value).toFixed(2);
    for (var i = 0; i < units.length; i++) {
      if (Math.abs(value) >= units[i][1]) {
        text = (value / units[i][1]).toFixed(2) + units[i][0];
        break;
      }
    }
    return currency ? text + " " + currency : text;
  }

  function pct(value) {
    if (value === null || value === undefined) return "–";
    return (value * 100).toFixed(2) + "%";
  }

  function gap(value) {
    if (value === null || value === undefined) return "–";
    return (Math.abs(value) * 100).toFixed(1) + "% " + (value >= 0 ? "above" : "below");
  }

  function addRow(cells) {
    var tr = document.createElement("tr");
    cells.forEach(function (text) {
      var td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    });
    valuationRows.appendChild(tr);
  }

  function renderStats(s) {
    setText("count-below", s.below);
    setText("count-same", s.same);
    setText("count-above", s.above);
    var counted = s.below + s.same + s.above;
    var note = "Of " + counted + " valuation" + (counted === 1 ? "" : "s") +
      "; within " + (s.threshold * 100) + "% of the price counts as about the same.";
    if (s.not_available) {
      note += " " + s.not_available + " couldn't be computed (shown as – below).";
    }
    setText("stats-note", note);
  }

  function renderValuation(v) {
    renderStats(v.summary);
    valuationRows.innerHTML = "";
    // With default assumptions the multiple methods use the stock's own
    // current multiple, so they land at ~the price; say so in the label.
    var used = v.multiples_used || {};
    var MULTIPLE_KEYS = { pe_multiple: "pe", ev_ebitda_multiple: "ev_ebitda", ps_multiple: "ps" };
    METHODS.forEach(function (m) {
      var e = v.estimates[m[0]] || {};
      var label = m[1];
      var key = MULTIPLE_KEYS[m[0]];
      if (key && used[key]) {
        label += " (" + Number(used[key]).toFixed(1) + "×, " + used[key + "_source"] + ")";
      }
      addRow([label, money(e.value_per_share, v.currency), gap(e.price_vs_estimate)]);
    });
    var r = v.estimates.reverse_dcf_implied_growth || {};
    addRow([
      "Reverse DCF: implied growth",
      pct(r.implied_growth),
      r.analyst_growth_5y === null || r.analyst_growth_5y === undefined
        ? "–" : "analyst 5y: " + pct(r.analyst_growth_5y)
    ]);
    var a = v.assumptions;
    setText("valuation-assumptions",
      "Assumptions: discount rate " + pct(a.discount_rate) + " (" + a.notes.discount_rate + "); " +
      "growth " + pct(a.growth) + " (" + a.notes.growth + "); " +
      "terminal growth " + pct(a.terminal_growth) + "; " + a.years + "-year horizon.");
    valuationBox.hidden = false;
  }

  function fetchJson(url) {
    return fetch(url).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.error || ("HTTP " + response.status));
        return body;
      });
    });
  }

  function loadValuation(symbol, id) {
    valuationBox.hidden = true;
    valuationStatus.className = "";
    valuationStatus.textContent = "Computing valuations…";
    fetchJson("/api/valuation?symbol=" + encodeURIComponent(symbol))
      .then(function (v) {
        if (id !== requestId) return;
        renderProfile(v);
        renderValuation(v);
        valuationStatus.textContent = "";
      })
      .catch(function (err) {
        if (id !== requestId) return;
        renderProfile(null);
        valuationStatus.className = "error";
        valuationStatus.textContent = "Valuation failed: " + err.message;
      });
  }

  function render(q) {
    setText("company-name", q.name || q.symbol);
    setText("current-price", money(q.price, q.currency));
    // The session date lives here now that day high/low sit on one line.
    setText("price-label", q.price_time ? "Current price as of " + q.price_time
      : q.session_date ? "Current price for the " + q.session_date + " session" : "Current price");
    setText("previous-close", money(q.previous_close, q.currency));
    renderRange("session-low", "session-high", "day-marker", "day-caption", "day",
      q.session_low, q.session_high, q);
    renderRange("week52-low", "week52-high", "week52-marker", "week52-caption", "52-week",
      q.week52_low, q.week52_high, q);
    var change = document.getElementById("price-change");
    if (q.change === null || q.change === undefined) {
      change.textContent = "Change: –";
      change.className = "change";
    } else {
      var sign = q.change > 0 ? "+" : q.change < 0 ? "−" : "";
      change.textContent = sign + money(Math.abs(q.change), "") + " (" + sign +
        (Math.abs(q.change_pct) * 100).toFixed(2) + "%) this session";
      change.className = "change" + (q.change > 0 ? " up" : q.change < 0 ? " down" : "");
    }
    // Market cap/sector/industry come from the (slower) fundamentals fetch in /api/valuation.
    setText("company-symbol", q.symbol + (q.exchange ? " (" + q.exchange + ")" : ""));
    setText("company-market-cap", "Market cap loading…");
    setText("company-pe", "P/E loading…");
    setText("company-dividend-yield", "Dividend yield loading…");
    setText("company-sector", "Sector loading…");
    setText("company-industry", "Industry loading…");
    result.hidden = false;
  }

  // Range bar (day or 52-week): low and high at the ends, a marker at the current price.
  function renderRange(lowId, highId, markerId, captionId, name, low, high, q) {
    var marker = document.getElementById(markerId);
    setText(lowId, money(low, q.currency));
    setText(highId, money(high, q.currency));
    var missing = low === null || low === undefined || high === null || high === undefined;
    if (missing || high < low) {
      marker.hidden = true;
      setText(captionId, name.charAt(0).toUpperCase() + name.slice(1) + " range not reported");
      return;
    }
    // A flat range (high == low, e.g. a single trade) puts the marker mid-bar.
    var position = high > low ? (q.price - low) / (high - low) : 0.5;
    // The range figures can lag the live price, so it may sit just
    // outside them; pin the marker to the nearer end.
    var clamped = Math.min(1, Math.max(0, position));
    marker.style.left = (clamped * 100) + "%";
    marker.hidden = false;
    var where = high === low ? "at the " + name + " low and high"
      : position > 1 ? "above the " + name + " high"
      : position < 0 ? "below the " + name + " low"
      : Math.round(position * 100) + "% of the way from low to high";
    marker.title = "Current price " + money(q.price, q.currency) + ", " + where;
    setText(captionId, "Current price " + money(q.price, q.currency) + " is " + where);
  }

  function renderProfile(v) {
    var cap = v && v.inputs ? v.inputs.market_cap : null;
    setText("company-market-cap", !v ? "Market cap unavailable"
      : cap === null || cap === undefined ? "Market cap not reported"
      : "Market cap " + bigMoney(cap, v.currency));
    var pe = v && v.inputs ? v.inputs.trailing_pe : null;
    setText("company-pe", !v ? "P/E unavailable"
      : pe === null || pe === undefined ? "P/E not reported"
      : "P/E " + Number(pe).toFixed(2) + " (trailing)");
    // Annual dividend per share over price, as stock_intrinsic_value.py computes it.
    var div = v && v.inputs ? v.inputs.dividend_rate : null;
    setText("company-dividend-yield", !v ? "Dividend yield unavailable"
      : div === null || div === undefined || !v.price ? "Dividend yield not reported"
      : "Dividend yield " + pct(div / v.price));
    setText("company-sector", !v ? "Sector unavailable" : (v.sector || "Sector not reported"));
    setText("company-industry", !v ? "Industry unavailable" : (v.industry || "Industry not reported"));
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var symbol = input.value.trim().toUpperCase();
    if (!symbol) return;

    button.disabled = true;
    status.className = "";
    status.textContent = "Looking up " + symbol + "…";

    var id = ++requestId;
    fetchJson("/api/quote?symbol=" + encodeURIComponent(symbol))
      .then(function (q) {
        if (id !== requestId) return;
        render(q);
        status.textContent = "";
        loadValuation(q.symbol, id);
      })
      .catch(function (err) {
        if (id !== requestId) return;
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
    price_time, session_date, session_high, session_low, previous_close,
    change, change_pct (a fraction), week52_low, week52_high. The 52-week
    range is Yahoo's ``fiftyTwoWeekLow``/``fiftyTwoWeekHigh`` from the chart
    ``meta`` block, None when Yahoo omits it. The price and session figures come from the chart ``meta`` block (which reflects
    an in-progress session); if Yahoo omits them, they fall back to the
    most recent settled daily bar. Raises requests.RequestException if
    Yahoo returns no usable price. previous_close / change / change_pct
    are None when the window has no bar before the latest session.
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

    # Movement for the latest session is measured against the close of the
    # last bar dated before it. The in-progress session's bar can already
    # carry a close, so "the second-to-last row" isn't reliable.
    earlier = [r for r in rows if session_date and r["date"] < session_date]
    previous_close = earlier[-1]["close"] if earlier else None
    change = change_pct = None
    if previous_close:
        change = round(price - previous_close, 4)
        change_pct = change / previous_close

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
        "previous_close": previous_close,
        "change": change,
        "change_pct": change_pct,
        "week52_low": meta.get("fiftyTwoWeekLow"),
        "week52_high": meta.get("fiftyTwoWeekHigh"),
    }


def get_valuation(symbol):
    """Run stock_intrinsic_value.py's pipeline for ``symbol`` with its default assumptions.

    Returns that script's ``--json`` payload (``build_json()``): inputs,
    assumptions, and every estimate with its gap to the price, plus a
    ``summary`` from summarize_estimates(). Raises
    requests.RequestException / ValueError / KeyError on a failed fetch,
    and ValueError when Yahoo returns no usable fundamentals.
    """
    modules = siv.fetch_fundamentals(symbol)
    inputs = siv.collect_inputs(modules)
    if inputs["price"] is None:
        raise ValueError("no usable fundamentals returned")
    args = siv.parse_args([symbol])
    assumptions = siv.resolve_assumptions(inputs, args)
    estimates, used = siv.compute_estimates(inputs, assumptions, args)
    payload = siv.build_json(symbol, inputs, assumptions, estimates, used)
    payload["summary"] = summarize_estimates(payload)
    return payload


def summarize_estimates(payload, threshold=SAME_THRESHOLD):
    """Count the per-share valuations below / about the same as / above the price.

    A valuation counts as "same" when it is less than ``threshold`` (a
    fraction of the price) away from it. Methods with no value (missing
    inputs) are counted in ``not_available`` instead. Returns
    ``{below, same, above, not_available, threshold}``.
    """
    price = payload["price"]
    counts = {"below": 0, "same": 0, "above": 0, "not_available": 0}
    for method in VALUATION_METHODS:
        value = payload["estimates"][method]["value_per_share"]
        if value is None or not price:
            counts["not_available"] += 1
        elif abs(value - price) / price < threshold:
            counts["same"] += 1
        elif value < price:
            counts["below"] += 1
        else:
            counts["above"] += 1
    counts["threshold"] = threshold
    return counts


class StockInfoHandler(BaseHTTPRequestHandler):
    """Serves the page at ``/`` and JSON at ``/api/quote`` and ``/api/valuation``."""

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
        if url.path == "/api/quote":
            lookup, what = get_stock_info, "quote"
        elif url.path == "/api/valuation":
            lookup, what = get_valuation, "valuation"
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        raw = parse_qs(url.query).get("symbol", [""])[0]
        try:
            symbol = normalize_symbol(raw)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        try:
            info = lookup(symbol)
        except (requests.RequestException, ValueError, KeyError) as exc:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"error": f"failed to fetch {what} for {symbol!r}: {exc}"},
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
