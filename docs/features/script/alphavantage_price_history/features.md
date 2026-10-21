# Alpha Vantage Price History

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use Alpha Vantage's TIME_SERIES_DAILY API (documented; needs a key).
- Read ALPHAVANTAGE_API_KEY from the environment, or from a .env file at the repo root via cli_utils.load_dotenv() (a real environment variable wins).
    - If the key is missing, fail before making any request.
- Use daily_prices.py's add_window_args(), resolve_window(), price_row(), in_window() and print_table(), and cli_utils.py's load_dotenv(), require_env() and die().
- Don't use yahoo_finance.py.

## Actions

- Run as python3 alphavantage_price_history.py from the repo root.
- Take:
    - {{Symbol}}: a ticker in Alpha Vantage notation (e.g. AAPL, TSCO.LON, MBG.DEX, MC.PAR, SHOP.TRT, RELIANCE.BSE).
    - The time window, one of:
        - The last N sessions.
        - A start date, and optionally an end date (default: today), both inclusive. Combined with the last N sessions, only the final N sessions in the window are kept.
        - Neither: the last 31 calendar days.
    - Whether to fetch the full history (premium keys only; default: the latest 100 sessions).
- Retrieve the daily prices.
    - Skip any session with no close.
    - Keep only the sessions in the window; for the last N sessions, keep only the final N.
    - There is no adjusted close: adj_close is always null.
    - Without the full history, add a note when the window starts before the 100 sessions returned.
    - Ignore Alpha Vantage's time zone (it reported US/Eastern for a BSE listing).
- Output:
    - Any notes.
    - {{Symbol}} Alpha Vantage {{Number of sessions}}
    - One row per session: {{Date}} {{Open}} {{High}} {{Low}} {{Close}} {{Volume}}
    - The most recent session's open, high, low and close.
    - With --json: {symbol, source, notes, prices: [{date, open, high, low, close, adj_close, volume}]}, the same row shape as stock_price_history.py.
- A refusal Alpha Vantage sends with HTTP 200 (an unknown symbol, a premium-only request, the daily limit) fails with its message; an empty answer fails too.
- Never show the API key: replace it with <redacted> in any error message.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
    - A date not in YYYY-MM-DD form, an end date without a start date, or an end before the start exits with code 1, before any network call.
