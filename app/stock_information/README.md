# Stock Information

A small local web app for looking up a single stock: type a ticker, click **Submit**, and see three sections: **Company** (name; symbol; sector · industry; market cap · P/E · dividend yield), **Price** (current price with its movement; previous close · day low · day high; 52-week low · 52-week high), and **Valuations** (a table of intrinsic-value estimates). It reuses the repo's scripts rather than re-implementing anything: [`yahoo_finance.py`](../../yahoo_finance.py) and `extract_rows()` from [`stock_close_history.py`](../../stock_close_history.py) for the quote, and the fetch → assumptions → estimates pipeline from [`stock_intrinsic_value.py`](../../stock_intrinsic_value.py) (which runs every [`valuation.py`](../../valuation.py) method) for the valuations.

See [`docs/features.md`](docs/features.md) for the feature spec this app was built against.

## Features

- **Symbol text box + Submit button** — enter a ticker in Yahoo notation (`AAPL`, `VOD.L`, `D05.SI`, `SAP.DE`, …); input is trimmed and upper-cased.
- **Company: name and symbol** — the name as the card's title with the symbol below it. The name comes from Yahoo's `longName` (falling back to `shortName`, then the symbol); the symbol is shown with its exchange.
- **Company: sector and industry, then market cap, P/E and dividend yield** — two lines, `Technology · Consumer Electronics` and `Market cap 3.45T USD · P/E 34.12 (trailing) · Dividend yield 0.45%`. Sector and industry are Yahoo's `summaryProfile.sector` and `.industry`; market cap is `price.marketCap` (`inputs.market_cap` in the valuation payload, abbreviated K/M/B/T, in the quote currency); P/E is the trailing P/E, `summaryDetail.trailingPE` (`inputs.trailing_pe`, the same figure the P/E-multiple valuation uses); dividend yield is `summaryDetail.dividendRate` (`inputs.dividend_rate`, annual dividend per share) divided by the price, the same ratio `stock_intrinsic_value.py` uses to flag a token dividend. Non-payers usually have no `dividendRate`, so they show "Dividend yield not reported". All five come from the fundamentals payload that `/api/valuation` already fetches, so they show "… loading" until that call returns, "… unavailable" if it fails, and "… not reported" if Yahoo leaves a field out. Yahoo has exactly one sub-sector level, the industry.
- **Price: current price** — Yahoo's `regularMarketPrice`, with currency and the "as of" time in the exchange's local timezone.
- **Price: movement for the latest session** — the change and % change versus the previous close, colored green/red. The previous close is the close of the last daily bar dated *before* the latest session. It's computed from the same chart response, not a second fetch, and is shown on the same line as the price.
- **Price: previous close, day low and day high** — one line, `Previous close 78.38 SGD · Day low 77.82 SGD · Day high 78.49 SGD`. High/low are Yahoo's `regularMarketDayHigh` / `regularMarketDayLow` for the latest session; the previous close is described above. The session they belong to is shown by the "Current price as of …" label under the price (from `regularMarketTime`, in exchange-local time), which falls back to the session date when Yahoo gives no market time.
- **Price: 52-week low and high** — one line, `52-week low 58.10 SGD · 52-week high 80.70 SGD`, from the chart `meta` block's `fiftyTwoWeekLow` / `fiftyTwoWeekHigh` (same `/api/quote` call, no extra fetch). Shows `–` if Yahoo omits them.
- **Valuations** — a table with each method's value per share and how far the price sits above/below it: two-stage DCF, dividend discount (Gordon), P/E multiple, Graham formula, EV/EBITDA multiple, P/S multiple, reported-EV → equity (a consistency check), plus the reverse-DCF implied growth rate. The assumptions used (discount rate, growth, terminal growth, horizon, and where each came from) are listed under the table. These are `stock_intrinsic_value.py`'s defaults; the page doesn't let you override them.

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
# Same JSON as `python3 stock_intrinsic_value.py D05.SI --json`:
# {"symbol": ..., "price": ..., "inputs": {...}, "assumptions": {...},
#  "multiples_used": {...}, "estimates": {"dcf_two_stage": {"value_per_share": ..., "price_vs_estimate": ...}, ...}}
```

## How it works

1. **Serve the page** — `GET /` returns `PAGE_HTML`: a text box, a Submit button, an empty status line, and a hidden result card.
2. **Submit** — the page's inline script calls `GET /api/quote?symbol=<SYMBOL>` on the same server.
3. **Fetch the quote** — the handler validates the symbol (`normalize_symbol`), then `get_stock_info` calls `yahoo_finance.build_params(range_="5d")` + `yahoo_finance.fetch_history()` (the same chart endpoint `stock_close_history.py` uses) and reads the price, name, and day high/low from the result's `meta` block. If Yahoo omits those fields, it falls back to the most recent settled daily bar from `stock_close_history.extract_rows()`.
4. **Render** — the browser fills in the result card from the JSON.
5. **Valuations** — once the quote is shown, the page calls `GET /api/valuation?symbol=<SYMBOL>`. `get_valuation` runs `stock_intrinsic_value.py`'s own functions in the same order as its `main()`: `fetch_fundamentals()` (Yahoo quoteSummary, with the crumb/cookie handshake), `collect_inputs()`, `resolve_assumptions()` and `compute_estimates()` with the script's default arguments, then returns `build_json()`, the same payload as `stock_intrinsic_value.py --json`. The page renders it as a table. It's a separate request so the price appears right away, even when the slower and more fragile fundamentals fetch fails.

A server is needed (instead of a static page like `app/hottest_discussions/`) because Yahoo's endpoints don't send CORS headers, so a browser can't call them directly.

## File structure

| File | Purpose |
|---|---|
| `stock_info_server.py` | The server and page — the only thing you run |
| `docs/features.md` | Feature spec this app implements |
| `README.md` | This documentation |

## API reference

- `normalize_symbol(value)` — Strips and upper-cases a ticker; raises `ValueError` unless it matches `SYMBOL_PATTERN` (1–20 of letters, digits, `.`, `-`, `^`, `=`).
- `get_stock_info(symbol)` — Returns `{name, symbol, exchange, currency, price, price_time, session_date, session_high, session_low, previous_close, change, change_pct, week52_low, week52_high}` (`change_pct` is a fraction; the 52-week fields are `None` when Yahoo's chart `meta` omits them; the three movement fields are `None` if the 5-day window has no bar before the latest session). Raises `requests.RequestException` on a Yahoo error or when no price is available.
- `get_valuation(symbol)` — Runs `stock_intrinsic_value.py`'s pipeline with its default assumptions and returns its `build_json()` payload. Raises `requests.RequestException` / `ValueError` / `KeyError` on a failed fetch, or `ValueError` when Yahoo returns no usable fundamentals.
- `StockInfoHandler` — `BaseHTTPRequestHandler` serving `/` (page), `/api/quote` and `/api/valuation` (JSON).
- `parse_args(argv=None)` — Parses `--host` and `--port`.
- `main(argv=None)` — Starts a `ThreadingHTTPServer` and serves until Ctrl+C.

## Tests

Covered offline by [`tests/test_stock_info_server.py`](../../tests/test_stock_info_server.py): `normalize_symbol`, `get_stock_info` (meta fields, gmtoffset dating, fallback to the latest bar, previous-close/change including an in-progress bar that already has a close, no earlier bar, 52-week range present/absent, no-price error), `get_valuation` (pipeline run over canned fundamentals incl. sector/industry, trailing P/E and dividend rate, no-price error), the HTTP handler's status codes for both endpoints, and `parse_args`. Run from the repo root with `python3 -m pytest`.

## Error handling

| Situation | HTTP status | Page shows |
|---|---|---|
| Empty or malformed symbol | 400 | `Lookup failed: invalid stock symbol '...'` |
| Unknown ticker / Yahoo error / network failure | 502 | `Lookup failed: failed to fetch quote for 'X': <reason>` |
| Valuation fetch fails (no fundamentals, crumb handshake fails, network) | 502 from `/api/valuation` | Quote stays visible; valuations section shows `Valuation failed: <reason>` |
| Unknown path | 404 | — |

Bad `--port` values are rejected by argparse (exit code 2).

## Notes / limitations

- Uses Yahoo Finance's **unofficial** chart endpoint — it can change or rate-limit without notice.
- No name → ticker resolution: the user must enter a Yahoo-notation ticker.
- "Current price" is Yahoo's last regular-market price; it's delayed for many exchanges and doesn't include pre/post-market trading. Outside trading hours, it and the session high/low refer to the last completed session.
- Valuations are **mechanical, not predictive**: pure arithmetic over Yahoo's fundamentals and default assumptions. With those defaults, the P/E, EV/EBITDA and P/S rows use the stock's *own* current multiple, so they land at about the current price by construction. The page labels them with the multiple and its source to make that visible. A method whose inputs are missing (e.g. no positive free cash flow, so no DCF, as is typical for banks) shows `–`.
- Binds to `127.0.0.1` by default. Passing `--host 0.0.0.0` exposes it on your network with no authentication.
