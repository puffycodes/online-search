# Stock Fundamental

## Requirement

- Reuse the shared modules and scripts in this project (rather than copying their logic) as much as possible.
    - Use stock_intrinsic_value.py's fetch_fundamentals() and collect_inputs() to retrieve and parse Yahoo Finance's quoteSummary data.
- Keep extract_indicators() importable, for the stock information web app.

## Actions

- Run as python3 stock_fundamental.py from the repo root.
- Take:
    - {{Symbol}}: a ticker in Yahoo notation, including the exchange suffix for non-US listings (e.g. AAPL, VOD.L, D05.SI, SAP.DE).
- Retrieve the stock's fundamentals.
- Compute the fundamental indicators, grouped:
    - Profitability: {{Gross Margin}} {{Operating Margin}} {{Net Margin}} {{Return on Equity}} {{Return on Assets}}
    - Growth: {{Revenue Growth}} {{Earnings Growth}} {{Analyst 5-Year Growth}}
    - Valuation: {{Trailing P/E}} {{Forward P/E}} {{PEG}} {{EV/EBITDA}} {{P/B}} {{P/S}} {{FCF Yield}}
    - Financial health: {{Debt/Equity}} {{Net Debt/EBITDA}} {{Current Ratio}} {{Quick Ratio}}
    - Cash flow: {{Free Cash Flow}} {{Operating Cash Flow}} {{Cash Conversion}}
    - Shareholder returns: {{Dividend Yield}} {{Payout Ratio}}
    - Derive PEG (trailing P/E / analyst 5-year growth in percent), FCF yield (free cash flow / market cap), net debt/EBITDA, cash conversion (free cash flow / net income) and dividend yield (dividend / price).
    - Convert Yahoo's debt/equity percentage into a ratio.
    - Leave an indicator blank when it is not reported, or not meaningful:
        - PEG with no or negative growth.
        - Net debt/EBITDA with non-positive EBITDA.
        - Cash conversion with non-positive net income.
        - A gross margin of exactly 0 (Yahoo's placeholder for banks).
- Output:
    - {{Company Name}} {{Symbol}} {{Exchange}} {{Currency}} {{Price}} {{Market Cap}} {{Sector}} {{Industry}}
    - One section per group, one row per indicator: {{Indicator}} {{Value}}, with percentages, ratios and abbreviated amounts.
    - With --json: {symbol, name, exchange, currency, sector, industry, price, market_cap, indicators}.
- The indicators are descriptive, not forecasts or advice.
- An unknown ticker, or no usable fundamentals, fails with an error.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option exits with code 2, before any network call.
