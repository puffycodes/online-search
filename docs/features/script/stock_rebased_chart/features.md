# Stock Rebased Comparison Chart

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use Yahoo Finance's chart endpoint (unofficial; no API key).
- Use yahoo_finance.py's build_params(), fetch_history(), extract_series() and meta_summary().
- Use indicators.py's rebase().
- Use matplotlib to draw the chart.

## Actions

- Run as python3 stock_rebased_chart.py from the repo root.
- Take:
    - {{Symbols}}: one or more tickers in Yahoo notation, e.g. AAPL MSFT VOD.L.
    - The time window, one of:
        - A range: 5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y or max (default: 6mo).
        - The last N sessions (cannot be combined with a range).
        - A start date, and optionally an end date (default: today). This overrides a range or last N.
    - The base date, where every series reads 100 (default: the first date of the first symbol's series).
    - The image path to write (default: rebased_chart.png), or open an interactive window instead.
- For each symbol, retrieve its daily closes, skipping sessions with no close.
    - If a symbol fails to fetch or has no close in the window, drop it with a warning on stderr and carry on.
- Rescale each series so its close on the base date is 100.
    - The base date must be a trading day in every series; a symbol with no close on that exact date is dropped with a warning.
- Draw all the rebased series on one chart, with a line at 100.
    - Above 100 means the stock has risen since the base date; below 100 means it has fallen.
- Output: "Wrote {{Image Path}}", plus a warning for each dropped symbol.
- If no symbol has data, or none has a close on the base date, fail with an error.
- On failure:
    - A runtime or data failure (including matplotlib not being installed) exits with code 1, with "Error: ..." on stderr.
    - An invalid option value exits with code 2, before any network call.
    - A date not in YYYY-MM-DD form exits with code 1 ("invalid date ..."), also before any network call.
