# Stock Risk

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use Yahoo Finance's chart endpoint (unofficial; no API key).
- Use yahoo_finance.py's add_window_args(), build_params(), fetch_history(), extract_series(), session_datetime() and meta_summary().
- Use indicators.py's volatility(), max_drawdown() and correlation().

## Actions

- Run as python3 stock_risk.py from the repo root.
- Take:
    - {{Symbols}}: one or more tickers in Yahoo notation, e.g. AAPL MSFT VOD.L BTC-USD. Repeats (in any letter case) are measured once.
    - The time window, one of:
        - A range: 5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y or max (default: 1y).
        - The last N sessions (cannot be combined with a range).
        - A start date, and optionally an end date (default: today). This replaces a range; combined with the last N sessions, the window starts at the start date and only the final N sessions in it are kept.
    - Optionally a {{Benchmark}} symbol (e.g. ^GSPC) to read the others against.
        - If it is also one of the {{Symbols}}, it is measured once, as the benchmark; if it is the only symbol, exit with code 2 before any network call.
    - Optionally JSON output.
- For each symbol and the benchmark, retrieve its daily closes, skipping sessions with no close.
    - Use the adjusted close (splits and dividends folded in) when every kept session has one; otherwise use the raw close for the whole series, never a mix.
    - If a symbol fails to fetch, has no close in the window, or has a price of zero or below, skip it, record the reason, and carry on.
- For each symbol and the benchmark, compute:
    - The number of sessions, the first and last dates and prices, and the change over the window.
    - The annualized volatility of its daily returns: over 365 sessions a year if the series has any weekend session (crypto), otherwise 252. Leave it empty with fewer than 3 sessions.
    - The maximum drawdown: the worst fall from a running high, with the date and price of that high and of the low after it, and the first date it closed back at or above the high (empty if not yet). All empty when it never fell below an earlier high.
    - The highest close in the window, its date, and how far the last close is below it.
- For every pair of symbols that loaded (the benchmark included), compute the correlation of their daily returns over the dates both traded, with the number of shared sessions and their first and last dates. Leave it empty with fewer than 3 shared sessions or when one series never moved.
- Output:
    - "Measuring risk for {{Symbols}}...", then for each symbol (and the benchmark, labelled "{{Benchmark}} (benchmark)"): the exchange and currency, sessions and dates, the price basis and sessions per year, the change, the volatility, the worst fall with its dates and recovery, and the distance from the high.
    - A table of the correlations, with the shared sessions for each pair.
    - A closing line that the figures describe the window measured and don't predict future swings.
    - A warning on stderr for each skipped symbol, with its reason.
    - With JSON output: {symbols, benchmark, correlations, skipped}, with no progress line. Fractions are not rounded; prices are rounded to 4 decimal places.
- If no symbol loaded (the benchmark alone does not count), fail with an error naming each symbol's reason.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with "Error: ..." on stderr, or {"error": "..."} with JSON output.
    - An invalid option value exits with code 2, before any network call.
    - A date not in YYYY-MM-DD form exits with code 1 ("invalid date ..."), also before any network call.
