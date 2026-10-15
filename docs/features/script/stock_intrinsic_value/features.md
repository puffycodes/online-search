# Stock Intrinsic Value

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use Yahoo Finance's quoteSummary endpoint (unofficial; needs a cookie and crumb, no API key).
- Use yahoo_finance.py's fetch_quote_summary() for the cookie, crumb and quoteSummary request.
- Use every valuation method in valuation.py.
- Keep fetch_fundamentals(), collect_inputs(), resolve_assumptions(), compute_estimates() and build_json() importable, for the stock information web app and stock_fundamental.py.

## Actions

- Run as python3 stock_intrinsic_value.py from the repo root.
- Take:
    - {{Symbol}}: a ticker in Yahoo notation, including the exchange suffix for non-US listings (e.g. AAPL, VOD.L, D05.SI, SAP.DE).
    - Optional assumptions (all fractions, e.g. 0.09 = 9%):
        - The discount rate (default: CAPM from the stock's beta, else 0.09).
        - The forecast growth (default: the analyst 5-year estimate, else the 1-year estimate, else 0.05).
        - The terminal growth (default: 0.025).
        - The forecast horizon in years (default: 10).
        - The risk-free rate and equity risk premium for CAPM (defaults: 0.04 and 0.05).
        - A fair P/E, EV/EBITDA or P/S multiple (default: the stock's current one).
- Retrieve the stock's fundamentals: price, cash flow, earnings, debt, dividend, beta, multiples, analyst growth, sector and industry.
- Resolve the assumptions, noting where each one came from.
    - If the terminal growth is not below the discount rate, raise the discount rate so the model stays defined.
- Compute each valuation whose inputs are present and positive; the rest are left blank:
    - Two-stage DCF, reverse DCF (the growth the price implies), dividend discount, P/E multiple, Graham formula, EV/EBITDA multiple, P/S multiple, and reported EV → equity (a data check).
- Output:
    - {{Company Name}} {{Symbol}} {{Exchange}} {{Currency}} {{Price}}
    - The fundamentals used.
    - The assumptions used, each with its source.
    - One row per method: {{Method}} {{Value per Share}} {{Price vs Estimate}}
    - With --json: {symbol, name, exchange, currency, sector, industry, price, inputs, assumptions, multiples_used, estimates}.
- The estimates are mechanical calculations from the assumptions, not forecasts or advice.
- An unknown ticker, or no usable fundamentals, fails with an error.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
