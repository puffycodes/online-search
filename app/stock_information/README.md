# Stock Information

A small local web app for looking up a single stock: type a ticker, click **Submit**, and see three sections: **Company** (name; symbol; sector · industry; market cap · P/E · dividend yield), **Price** (current price, its movement and the previous close; then day-range and 52-week-range bars, each with a marker at the current price), and **Valuations** (how many estimates say the price is undervalued / fair value / overvalued, then a table of intrinsic-value estimates). It reuses the repo's scripts rather than re-implementing anything: [`yahoo_finance.py`](../../yahoo_finance.py) and `extract_rows()` from [`stock_price_history.py`](../../stock_price_history.py) for the quote, and the fetch → assumptions → estimates pipeline from [`stock_intrinsic_value.py`](../../stock_intrinsic_value.py) (which runs every [`valuation.py`](../../valuation.py) method) for the valuations.

See [`docs/features.md`](docs/features.md) for the feature spec this app was built against.

## Features

- **Symbol text box + Submit button** — enter a ticker in Yahoo notation (`AAPL`, `VOD.L`, `D05.SI`, `SAP.DE`, …); input is trimmed and upper-cased.
- **Company: name and symbol** — the name as the card's title with the symbol below it. The name comes from Yahoo's `longName` (falling back to `shortName`, then the symbol); the symbol is shown with its exchange.
- **Company: sector and industry, then market cap, P/E and dividend yield** — two lines, `Technology · Consumer Electronics` and `Market cap 3.45T USD · P/E 34.12 (trailing) · Dividend yield 0.45%`. Sector and industry are Yahoo's `summaryProfile.sector` and `.industry`; market cap is `price.marketCap` (`inputs.market_cap` in the valuation payload, abbreviated K/M/B/T, in the quote currency); P/E is the trailing P/E, `summaryDetail.trailingPE` (`inputs.trailing_pe`, the same figure the P/E-multiple valuation uses); dividend yield is `summaryDetail.dividendRate` (`inputs.dividend_rate`, annual dividend per share) divided by the price, the same ratio `stock_intrinsic_value.py` uses to flag a token dividend. Non-payers usually have no `dividendRate`, so they show "Dividend yield not reported". All five come from the fundamentals payload that `/api/valuation` already fetches, so they show "… loading" until that call returns, "… unavailable" if it fails, and "… not reported" if Yahoo leaves a field out. Yahoo has exactly one sub-sector level, the industry.
- **Price: current price** — Yahoo's `regularMarketPrice`, with currency and the "as of" time in the exchange's local timezone.
- **Price: movement for the latest session** — the change and % change versus the previous close, colored green/red. The previous close is the close of the last daily bar dated *before* the latest session. It's computed from the same chart response, not a second fetch, and is shown on the same line as the price, followed by the previous close itself.
- **Price: day range bar** — a horizontal bar with the day low at its left end and the day high at its right, and a marker at the current price, e.g. `77.82 SGD ━━●━━━━━━ 78.49 SGD`, with a caption saying where the price sits (same wording as the 52-week bar below). High/low are Yahoo's `regularMarketDayHigh` / `regularMarketDayLow` for the latest session. A flat range (high equal to low) puts the marker mid-bar; a price outside the range pins it to the nearer end; if Yahoo reports no day high/low at all, the caption reads "Day range not reported". The session they belong to is shown by the "Current price as of …" label under the price (from `regularMarketTime`, in exchange-local time), which falls back to the session date when Yahoo gives no market time.
- **Price: 52-week range bar** — a horizontal bar with the 52-week low at its left end and the 52-week high at its right, and a marker at the current price, e.g. `58.10 SGD ━━━━━━●━━ 80.70 SGD`. A caption underneath says where the price sits (`Current price 77.84 SGD is 87% of the way from low to high`). The low/high come from the chart `meta` block's `fiftyTwoWeekLow` / `fiftyTwoWeekHigh` (same `/api/quote` call, no extra fetch). Those can lag the live price by a session, so a price outside the range pins the marker to the nearer end and the caption says "above the 52-week high" / "below the 52-week low". If Yahoo omits either figure, the ends show `–`, the marker is hidden and the caption reads "52-week range not reported".
- **Valuations: undervalued / fair value / overvalued counts** — three tiles above the table, in that order, counting how many of the seven per-share estimates (all table rows except the reverse DCF, which is a growth rate, not a value) put the price below, at, or above the estimate. An estimate above the price counts as **undervalued**, one below it as **overvalued**, and one less than 1% away from the price (`FAIR_VALUE_THRESHOLD`) as **fair value**, so an estimate exactly 1% away counts as under/overvalued. A note under the tiles says how many were counted and how many couldn't be computed (missing inputs). With default assumptions the three multiple-based rows land at about the price by construction, so they usually show up as "fair value". The counts are computed server-side by `summarize_estimates()` and returned as `summary` in `/api/valuation`.
- **Valuations: table** — each method's value per share and how far the price sits above/below it: two-stage DCF, dividend discount (Gordon), P/E multiple, Graham formula, EV/EBITDA multiple, P/S multiple, reported-EV → equity (a consistency check), plus the reverse-DCF implied growth rate. The assumptions used (discount rate, growth, terminal growth, horizon, and where each came from) are listed under the table. These are `stock_intrinsic_value.py`'s defaults; the page doesn't let you override them.

## Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/)

```bash
pip install requests
```

No web framework — the server is the standard library's `http.server`, and the page is a single inline HTML/CSS/JS string.

## Usage

Run from anywhere; the repo root is resolved relative to the script.

```bash
python3 app/stock_information/stock_info_server.py [--host HOST] [--port PORT]
```

| Flag | Default | Description |
|---|---|---|
| `--host HOST` | `127.0.0.1` | Interface to bind (localhost only by default) |
| `--port PORT` | `8000` | Port to listen on |

Example:

```bash
python3 app/stock_information/stock_info_server.py
# Serving Stock Information at http://127.0.0.1:8000/ (Ctrl+C to stop)
```

Then open <http://127.0.0.1:8000/>, type a symbol, and click **Submit**.

The JSON endpoint can also be called directly:

```bash
curl "http://127.0.0.1:8000/api/quote?symbol=D05.SI"
# {"name": "DBS Group Holdings Ltd", "symbol": "D05.SI", "exchange": "SES", "currency": "SGD",
#  "price": 77.84, "price_time": "2026-09-30 16:12 SGT", "session_date": "2026-09-30",
#  "session_high": 78.49, "session_low": 77.82, "previous_close": 78.38, "change": -0.57,
#  "change_pct": -0.00727, "week52_low": ..., "week52_high": ...}

curl "http://127.0.0.1:8000/api/valuation?symbol=D05.SI"
# Same JSON as `python3 stock_intrinsic_value.py D05.SI --json`, plus a "summary" key:
# {"symbol": ..., "price": ..., "inputs": {...}, "assumptions": {...},
#  "multiples_used": {...}, "estimates": {"dcf_two_stage": {"value_per_share": ..., "price_vs_estimate": ...}, ...},
#  "summary": {"undervalued": ..., "fair_value": ..., "overvalued": ..., "not_available": ..., "threshold": 0.01}}
```

## How it works

1. **Serve the page** — `GET /` returns `PAGE_HTML`: a text box, a Submit button, an empty status line, and a hidden result card.
2. **Submit** — the page's inline script calls `GET /api/quote?symbol=<SYMBOL>` on the same server.
3. **Fetch the quote** — the handler validates the symbol (`normalize_symbol`), then `get_stock_info` calls `yahoo_finance.build_params(range_="5d")` + `yahoo_finance.fetch_history()` (the same chart endpoint `stock_price_history.py` uses) and reads the price, name, day high/low and 52-week low/high from the result's `meta` block. If Yahoo omits the price or day fields, it falls back to the most recent settled daily bar from `stock_price_history.extract_rows()`.
4. **Render** — the browser fills in the result card from the JSON and positions the day-range and 52-week-range markers. Market cap, P/E, dividend yield, sector and industry show "… loading" until step 5 returns.
5. **Valuations** — once the quote is shown, the page calls `GET /api/valuation?symbol=<SYMBOL>`. `get_valuation` runs `stock_intrinsic_value.py`'s own functions in the same order as its `main()`: `fetch_fundamentals()` (Yahoo quoteSummary, with the crumb/cookie handshake), `collect_inputs()`, `resolve_assumptions()` and `compute_estimates()` with the script's default arguments, then returns `build_json()`, the same payload as `stock_intrinsic_value.py --json`, with a `summary` of undervalued/fair-value/overvalued counts added by `summarize_estimates()`. The page renders the counts as tiles and the estimates as a table. It's a separate request so the price appears right away, even when the slower and more fragile fundamentals fetch fails.

A server is needed (rather than a static page) because Yahoo's endpoints don't send CORS headers, so a browser can't call them directly. It also lets the page run the repo's scripts instead of a JavaScript copy of them, the same reason `app/hottest_discussions/` is a server.

## File structure

| File | Purpose |
|---|---|
| `stock_info_server.py` | The server and page — the only thing you run |
| `docs/features.md` | Feature spec this app implements |
| `README.md` | This documentation |

## API reference

- `normalize_symbol(value)` — Strips and upper-cases a ticker; raises `ValueError` unless it matches `SYMBOL_PATTERN` (1–20 of letters, digits, `.`, `-`, `^`, `=`).
- `get_stock_info(symbol)` — Returns `{name, symbol, exchange, currency, price, price_time, session_date, session_high, session_low, previous_close, change, change_pct, week52_low, week52_high}` (`change_pct` is a fraction; the 52-week fields are `None` when Yahoo's chart `meta` omits them; the three movement fields are `None` if the 5-day window has no bar before the latest session). Raises `requests.RequestException` on a Yahoo error or when no price is available.
- `get_valuation(symbol)` — Runs `stock_intrinsic_value.py`'s pipeline with its default assumptions and returns its `build_json()` payload plus `summary` (from `summarize_estimates`). Raises `requests.RequestException` / `ValueError` / `KeyError` on a failed fetch, or `ValueError` when Yahoo returns no usable fundamentals.
- `summarize_estimates(payload, threshold=FAIR_VALUE_THRESHOLD)` — Counts the `VALUATION_METHODS` estimates in a `build_json()` payload that are above the price (undervalued), within `threshold` (a fraction, default 1%) of it (fair value), or below it (overvalued), plus those with no value. Returns `{undervalued, fair_value, overvalued, not_available, threshold}`.
- `StockInfoHandler` — `BaseHTTPRequestHandler` serving `/` (page), `/api/quote` and `/api/valuation` (JSON).
- `parse_args(argv=None)` — Parses `--host` and `--port`.
- `main(argv=None)` — Starts a `ThreadingHTTPServer` and serves until Ctrl+C.

## Tests

Covered offline by [`tests/test_stock_info_server.py`](../../tests/test_stock_info_server.py): `normalize_symbol`, `get_stock_info` (meta fields, gmtoffset dating, fallback to the latest bar, previous-close/change including an in-progress bar that already has a close, no earlier bar, 52-week range present/absent, no-price error), `get_valuation` (pipeline run over canned fundamentals incl. sector/industry, trailing P/E and dividend rate, and its undervalued/fair-value/overvalued `summary`; no-price error), `summarize_estimates` (counting incl. the exact-1% boundary, negative and missing values, custom threshold), the HTTP handler's status codes for both endpoints, and `parse_args`. Run from the repo root with `python3 -m pytest`.

## Error handling

| Situation | HTTP status | Page shows |
|---|---|---|
| Empty or malformed symbol | 400 | `Lookup failed: invalid stock symbol '...'` |
| Unknown ticker / Yahoo error / network failure | 502 | `Lookup failed: failed to fetch quote for 'X': <reason>` |
| Valuation fetch fails (no fundamentals, crumb handshake fails, network) | 502 from `/api/valuation` | Quote stays visible; valuations section shows `Valuation failed: <reason>`; sector, industry, market cap, P/E and dividend yield show "… unavailable" |
| Unknown path | 404 | — |

Bad `--port` values are rejected by argparse (exit code 2).

## Notes / limitations

- Uses Yahoo Finance's **unofficial** chart endpoint — it can change or rate-limit without notice.
- No name → ticker resolution: the user must enter a Yahoo-notation ticker.
- "Current price" is Yahoo's last regular-market price; it's delayed for many exchanges and doesn't include pre/post-market trading. Outside trading hours, it and the day high/low refer to the last completed session.
- Valuations are **mechanical, not predictive**: pure arithmetic over Yahoo's fundamentals and default assumptions. With those defaults, the P/E, EV/EBITDA and P/S rows use the stock's *own* current multiple, so they land at about the current price by construction. The page labels them with the multiple and its source to make that visible. A method whose inputs are missing (e.g. no positive free cash flow, so no DCF, as is typical for banks) shows `–` and is counted as not available rather than under/fair/overvalued. The undervalued / fair value / overvalued tiles are a tally of those mechanical estimates, not a judgment that the stock is actually mispriced and not a buy/sell signal.
- Binds to `127.0.0.1` by default. Passing `--host 0.0.0.0` exposes it on your network with no authentication.
