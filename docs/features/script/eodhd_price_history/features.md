# EODHD Price History

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use EODHD's end-of-day API (documented; needs a key).
- Read EODHD_API_KEY from the environment, or from a .env file at the repo root via cli_utils.load_dotenv() (a real environment variable wins).
    - If the key is missing, fail before making any request.
- Use daily_prices.py's add_window_args(), resolve_window(), price_row(), in_window() and print_table(), and cli_utils.py's load_dotenv(), require_env() and die().
- Don't use yahoo_finance.py.

## Actions

- Run as python3 eodhd_price_history.py from the repo root.
- Take:
    - {{Symbol}}: a ticker in EODHD notation, SYMBOL.EXCHANGE (e.g. AAPL.US, VOD.LSE, 0700.HK), or an index (GSPC.INDX), currency pair (EURUSD.FOREX) or crypto coin (BTC-USD.CC).
    - The time window, one of:
        - The last N sessions.
        - A start date, and optionally an end date (default: today), both inclusive. Combined with the last N sessions, only the final N sessions in the window are kept.
        - Neither: the last 31 calendar days.
- Retrieve the daily prices for the window.
    - Skip any session with no close.
    - Drop any session outside the window (the free plan answers a request older than a year with one recent bar).
    - Report any warning EODHD attaches to the data as a note, once.
    - For the last N sessions, keep only the final N.
- Output:
    - Any notes.
    - {{Symbol}} EODHD {{Number of sessions}}
    - One row per session: {{Date}} {{Open}} {{High}} {{Low}} {{Close}} {{Adjusted Close}} (only when it differs from the close) {{Volume}}
    - The most recent session's open, high, low and close.
    - With --json: {symbol, source, notes, prices: [{date, open, high, low, close, adj_close, volume}]}, the same row shape as stock_price_history.py.
- An unknown ticker fails with EODHD's message ("HTTP 404: Ticker Not Found.").
- Never show the API key: replace it with <redacted> in any error message.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
    - A date not in YYYY-MM-DD form, an end date without a start date, or an end before the start exits with code 1, before any network call.
