# Stock Information

A small local web app for looking up a single stock: type a ticker, click **Submit**, and see the company name, symbol, current price, and the high/low of the latest session with its date. It reuses the repo's Yahoo Finance helpers — [`yahoo_finance.py`](../../yahoo_finance.py) and `extract_rows()` from [`stock_close_history.py`](../../stock_close_history.py) — rather than re-implementing the fetch.

See [`docs/features.md`](docs/features.md) for the feature spec this app was built against.

## Features

- **Symbol text box + Submit button** — enter a ticker in Yahoo notation (`AAPL`, `VOD.L`, `D05.SI`, `SAP.DE`, …); input is trimmed and upper-cased.
- **Company name and symbol** — the name comes from Yahoo's `longName` (falling back to `shortName`, then the symbol), shown with the exchange.
- **Current price** — Yahoo's `regularMarketPrice`, with currency and the "as of" time in the exchange's local timezone.
- **Latest session high / low with date** — Yahoo's `regularMarketDayHigh` / `regularMarketDayLow`, dated by `regularMarketTime` in exchange-local time.

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
#  "session_high": 78.49, "session_low": 77.82}
```

## How it works

1. **Serve the page** — `GET /` returns `PAGE_HTML`: a text box, a Submit button, an empty status line, and a hidden result card.
2. **Submit** — the page's inline script calls `GET /api/quote?symbol=<SYMBOL>` on the same server.
3. **Fetch the quote** — the handler validates the symbol (`normalize_symbol`), then `get_stock_info` calls `yahoo_finance.build_params(range_="5d")` + `yahoo_finance.fetch_history()` (the same chart endpoint `stock_close_history.py` uses) and reads the price, name, and day high/low from the result's `meta` block. If Yahoo omits those fields, it falls back to the most recent settled daily bar from `stock_close_history.extract_rows()`.
4. **Render** — the browser fills in the result card from the JSON.

A server is needed (instead of a static page like `app/hottest_discussions/`) because Yahoo's endpoints don't send CORS headers, so a browser can't call them directly.

## File structure

| File | Purpose |
|---|---|
| `stock_info_server.py` | The server and page — the only thing you run |
| `docs/features.md` | Feature spec this app implements |
| `README.md` | This documentation |

## API reference

- `normalize_symbol(value)` — Strips and upper-cases a ticker; raises `ValueError` unless it matches `SYMBOL_PATTERN` (1–20 of letters, digits, `.`, `-`, `^`, `=`).
- `get_stock_info(symbol)` — Returns `{name, symbol, exchange, currency, price, price_time, session_date, session_high, session_low}`. Raises `requests.RequestException` on a Yahoo error or when no price is available.
- `StockInfoHandler` — `BaseHTTPRequestHandler` serving `/` (page) and `/api/quote` (JSON).
- `parse_args(argv=None)` — Parses `--host` and `--port`.
- `main(argv=None)` — Starts a `ThreadingHTTPServer` and serves until Ctrl+C.

## Tests

Covered offline by [`tests/test_stock_info_server.py`](../../tests/test_stock_info_server.py): `normalize_symbol`, `get_stock_info` (meta fields, gmtoffset dating, fallback to the latest bar, no-price error), the HTTP handler's status codes, and `parse_args`. Run from the repo root with `python3 -m pytest`.

## Error handling

| Situation | HTTP status | Page shows |
|---|---|---|
| Empty or malformed symbol | 400 | `Lookup failed: invalid stock symbol '...'` |
| Unknown ticker / Yahoo error / network failure | 502 | `Lookup failed: failed to fetch quote for 'X': <reason>` |
| Unknown path | 404 | — |

Bad `--port` values are rejected by argparse (exit code 2).

## Notes / limitations

- Uses Yahoo Finance's **unofficial** chart endpoint — it can change or rate-limit without notice.
- No name → ticker resolution: the user must enter a Yahoo-notation ticker.
- "Current price" is Yahoo's last regular-market price; it's delayed for many exchanges and doesn't include pre/post-market trading. Outside trading hours, it and the session high/low refer to the last completed session.
- Binds to `127.0.0.1` by default. Passing `--host 0.0.0.0` exposes it on your network with no authentication.
