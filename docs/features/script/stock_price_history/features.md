# Stock Price History

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use price_source.py's fetch_history() for the data: EODHD (EODHD_API_KEY), or Alpha Vantage (ALPHAVANTAGE_API_KEY) for Indian tickers, chosen from the Yahoo-notation ticker. Until 2026-10-21 this used Yahoo Finance's chart endpoint, which fails the source audit.
- Show any notes price_source returns (e.g. a free plan returning less history than asked).
- Use yahoo_finance.py's add_window_args(), build_params(), extract_series(), session_datetime() and meta_summary().

## Actions

- Run as python3 stock_price_history.py from the repo root.
- Take:
    - {{Symbol}}: a ticker in Yahoo notation, including the exchange suffix for non-US listings (e.g. AAPL, VOD.L, SAP.DE, RELIANCE.NS). Singapore (.SI), Tokyo (.T) and futures (=F) aren't supported for now and fail before any request.
    - The time window, one of:
        - A range: 5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y or max (default: 1mo).
        - The last N sessions (cannot be combined with a range).
        - A start date, and optionally an end date (default: today). This replaces a range; combined with the last N sessions, the window starts at the start date and only the final N sessions in it are kept.
- Retrieve the daily prices for the window.
    - Keep only settled sessions: skip any session with no close (in progress, or a data gap).
    - Date each session by the exchange's local trading day.
    - For the last N sessions, keep only the final N.
- Output:
    - {{Symbol}} {{Exchange}} {{Currency}}
    - One row per session: {{Date}} {{Open}} {{High}} {{Low}} {{Close}} {{Adjusted Close}} (only when it differs from the close) {{Volume}}
    - The most recent session's open, high, low and close.
    - With --json: {symbol, exchange, currency, source, notes, prices: [{date, open, high, low, close, adj_close, volume}]}.
- An unknown ticker fails with the provider's message (EODHD's "Ticker Not Found.").
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
    - A date not in YYYY-MM-DD form exits with code 1 ("invalid date ..."), also before any network call.
