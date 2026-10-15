# Stock Earnings Calendar

## Requirement

- Reuse the shared modules and scripts in this project (rather than copying their logic) as much as possible.
    - Use yahoo_finance.py's fetch_quote_summary() to retrieve Yahoo Finance's quoteSummary data, and its summary_num() / summary_text() to read it.

## Actions

- Run as python3 stock_earnings_calendar.py from the repo root.
- Take:
    - {{Symbol}}: a ticker in Yahoo notation, including the exchange suffix for non-US listings (e.g. AAPL, VOD.L, D05.SI, SAP.DE).
- Retrieve the stock's calendar events, earnings history and price details.
- Report three sections:
    - Next earnings: {{Date}} {{Time (UTC)}} {{Confirmed or Estimated}} {{Upcoming or Past}} {{EPS Estimate (low, average, high)}} {{Revenue Estimate (low, average, high)}}
        - When Yahoo gives two dates, the earnings date is an estimated window: report its start and end.
    - Dividend: {{Ex-Dividend Date}} {{Payment Date}}, each flagged upcoming or past, and {{Last Dividend Amount}} with its ex-date.
        - Yahoo keeps the last dividend's dates until new ones are announced, so a date can be in the past.
        - For minor-unit listings (GBp, ILA, ZAc), give no currency for the amount: Yahoo does not say which currency it is in.
    - Earnings history: one row per quarter (up to four), oldest first: {{Quarter End}} {{Fiscal Quarter}} {{Reported Date}} {{EPS Estimate}} {{EPS Actual}} {{Surprise}}
- State the trading currency and the reporting currency; EPS and revenue estimates are in the reporting currency, which can differ (e.g. VOD.L trades in GBp and reports in EUR).
- Output:
    - {{Company Name}} {{Symbol}} {{Exchange}} {{Currency}}
    - One section per part above; a missing part says Yahoo has no data for it.
    - With --json: {symbol, name, exchange, currency, reporting_currency, next_earnings, dividend, earnings_history}.
- An unknown ticker fails with an error. So does a symbol with no next earnings date and no earnings history (an ETF, index, currency or future).
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option exits with code 2, before any network call.
