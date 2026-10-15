# Stock Earnings Calendar

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_earnings_calendar.py script to retrieve the earnings calendar.

## Actions

- Take one or more stocks named by the user.
    - Resolve each company to its Yahoo Finance ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - If unsure of the ticker, say so rather than guess.
    - Only company stocks report earnings; for an ETF, index, currency or commodity, say so instead of retrieving anything.
- Retrieve the earnings calendar, once per ticker.
    - If the ticker is unknown or has no earnings data, report the error.
    - Retry at most once, only for a transient network error.
- Output:
    - Answer the question asked first:
        - "When does it report?": {{Next Earnings Date}}, {{Time (UTC)}} if confirmed, whether it is confirmed or an estimated window, and {{EPS Estimate}} {{Revenue Estimate}} in the {{Reporting Currency}}.
        - "Did it beat?": the latest quarter's {{EPS Estimate}} {{EPS Actual}} {{Surprise}}, and the pattern across the quarters shown.
        - Dividend dates: {{Ex-Dividend Date}} {{Payment Date}} with whether each is upcoming or past, and {{Last Dividend Amount}}. A past ex-dividend date means the next one is not announced yet.
    - For a general request, all three parts briefly, with the history as a table: {{Quarter}} {{Reported}} {{Estimate}} {{Actual}} {{Surprise}}
    - For several companies, one table sorted by next earnings date.
    - A short caveat: dates and estimates are from Yahoo Finance and can change; check the company's investor-relations page before acting on one.
- If a part has no data, say so plainly.
- Never fabricate dates, estimates or results.
