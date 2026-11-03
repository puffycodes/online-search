# Stock Analyst Targets

## Requirement

- Reuse the shared modules and scripts in this project (rather than copying their logic) as much as possible.
    - Get the data through stock_data.py's analyst_view(), never from a provider directly, so the script reads only stock_data's neutral shape. It is served by yahoo_finance.py's analyst_view() (Yahoo Finance's quoteSummary) today.

## Actions

- Run as python3 stock_analyst_targets.py from the repo root.
- Take:
    - {{Symbol}}: a ticker in Yahoo notation, including the exchange suffix for non-US listings (e.g. AAPL, VOD.L, D05.SI, SAP.DE).
    - --days {{Days}} (default 90, a positive integer): how far back to list analyst actions.
- Retrieve the stock's analyst data and price.
- Report:
    - Price targets: {{Low}} {{Median}} {{Mean}} {{High}}, each with its {{Upside}} versus the current price (a fraction; negative is downside).
        - The price is Yahoo's current price, falling back to the regular-market price.
        - With no price, leave the upside blank.
    - Consensus: {{Recommendation}} (strong buy, buy, hold, underperform, sell) and its {{Mean Score}} on a 1 (strong buy) to 5 (strong sell) scale.
    - {{Number of Analysts}} with a price target.
    - Recommendation trend: one row per month (this month and up to three before), newest first: {{Strong Buy}} {{Buy}} {{Hold}} {{Sell}} {{Strong Sell}} {{Total}}
    - Analyst actions in the last {{Days}} days, newest first: {{Date}} (UTC) {{Firm}} {{Action}} (upgrade, downgrade, initiate, reiterate, maintain) {{From Grade}} {{To Grade}} {{Target Action}} (raised, lowered, maintained, announced, adjusted) {{Prior Target}} {{Target}}
        - A blank grade or a zero target from Yahoo is left blank.
        - With them, a summary: {{Upgrades}} {{Downgrades}} {{Initiations}} {{Targets Raised}} {{Targets Lowered}}
        - Yahoo has actions for US listings only.
- Output:
    - {{Company Name}} {{Symbol}} {{Exchange}} {{Currency}} {{Price}} {{Number of Analysts}}
    - One section per part above; a missing part says Yahoo has no data for it.
    - With --json: {symbol, name, exchange, currency, price, analysts, targets, upside, recommendation, trend, actions_days, action_summary, actions}.
- These are analysts' opinions as Yahoo aggregates them, not a forecast or advice.
- An unknown ticker fails with an error. So does a symbol with no targets, no recommendation, no trend and no actions (no analyst coverage, or an ETF, index, currency or future).
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option exits with code 2, before any network call.
