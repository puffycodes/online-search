# Stock Price History

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use Yahoo Finance's chart endpoint (unofficial; no API key).
- Use yahoo_finance.py's build_params(), fetch_history(), extract_series() and meta_summary().

## Actions

- Run as python3 stock_close_history.py from the repo root.
- Take:
    - {{Symbol}}: a ticker in Yahoo notation, including the exchange suffix for non-US listings (e.g. AAPL, VOD.L, D05.SI, SAP.DE).
    - The time window, one of:
        - A range: 5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y or max (default: 1mo).
        - The last N sessions (cannot be combined with a range).
        - A start date, and optionally an end date (default: today). This overrides a range or last N.
- Retrieve the daily prices for the window.
    - Keep only settled sessions: skip any session with no close (in progress, or a data gap).
    - Date each session by the exchange's local trading day.
    - For the last N sessions, keep only the final N.
- Output:
    - {{Symbol}} {{Exchange}} {{Currency}}
    - One row per session: {{Date}} {{Open}} {{High}} {{Low}} {{Close}} {{Adjusted Close}} (only when it differs from the close) {{Volume}}
    - The most recent session's open, high, low and close.
    - With --json: {symbol, exchange, currency, prices: [{date, open, high, low, close, adj_close, volume}]}.
- An unknown ticker fails with Yahoo's error message.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
    - A date not in YYYY-MM-DD form exits with code 1 ("invalid date ..."), also before any network call.
