# Stock Analyst Targets

## Requirement

- Reuse the shared modules and scripts in this project (rather than copying their logic) as much as possible.
    - Use yahoo_finance.py's fetch_quote_summary() to retrieve Yahoo Finance's quoteSummary data, and its summary_num() / summary_text() to read it.

## Actions

- Run as python3 stock_analyst_targets.py from the repo root.
- Take:
    - {{Symbol}}: a ticker in Yahoo notation, including the exchange suffix for non-US listings (e.g. AAPL, VOD.L, D05.SI, SAP.DE).
- Retrieve the stock's analyst data and price.
- Report:
    - Price targets: {{Low}} {{Median}} {{Mean}} {{High}}, each with its {{Upside}} versus the current price (a fraction; negative is downside).
        - The price is Yahoo's current price, falling back to the regular-market price.
        - With no price, leave the upside blank.
    - Consensus: {{Recommendation}} (strong buy, buy, hold, underperform, sell) and its {{Mean Score}} on a 1 (strong buy) to 5 (strong sell) scale.
    - {{Number of Analysts}} with a price target.
    - Recommendation trend: one row per month (this month and up to three before), newest first: {{Strong Buy}} {{Buy}} {{Hold}} {{Sell}} {{Strong Sell}} {{Total}}
- Output:
    - {{Company Name}} {{Symbol}} {{Exchange}} {{Currency}} {{Price}} {{Number of Analysts}}
    - One section per part above; a missing part says Yahoo has no data for it.
    - With --json: {symbol, name, exchange, currency, price, analysts, targets, upside, recommendation, trend}.
- These are analysts' opinions as Yahoo aggregates them, not a forecast or advice.
- An unknown ticker fails with an error. So does a symbol with no targets, no recommendation and no trend (no analyst coverage, or an ETF, index, currency or future).
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option exits with code 2, before any network call.
