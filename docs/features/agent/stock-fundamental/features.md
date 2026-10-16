# Stock Fundamental

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_fundamental.py script to retrieve the fundamental indicators.

## Actions

- Take one or more stocks named by the user.
    - Resolve each company to its Yahoo Finance ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - If unsure of the ticker, say so rather than guess.
- Retrieve the fundamental indicators, once per ticker.
    - `no fundamentals in response` can mean an unknown ticker or a temporary Yahoo glitch: for a ticker you're confident of, retry once before reporting it; for one you guessed, say it may be wrong.
    - If the ticker is unknown, report the error.
    - Retry at most once in total: for that error, or a transient network error.
- Output:
    - {{Company Name}} {{Symbol}} {{Sector}} {{Industry}} {{Price}} {{Market Cap}}
    - If the user asked about specific indicators, answer those first, with only the related context that helps.
    - Otherwise, a short read of each group (profitability, growth, valuation, financial health, cash flow, shareholder returns), then a table of all the indicators.
    - Interpret the figures against what is typical for the company's industry, and say when a figure can mislead.
    - {{Missing Indicators}}, named rather than skipped.
    - A short caveat: trailing figures from one Yahoo Finance snapshot, descriptive rather than predictive, not investment advice.
- Never fabricate figures.
