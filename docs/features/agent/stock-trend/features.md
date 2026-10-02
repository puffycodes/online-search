# Stock Trend

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_price_history.py script to retrieve the closing prices, and the trend() and moving_average() functions in indicators.py to classify them.

## Actions

- Take a stock named by the user.
    - Resolve the company to its Yahoo Finance ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - If unsure of the ticker, say so rather than guess.
- Pick the time window from what the user asked:
    - "lately", "recently", "right now", "this quarter" → the past 3 months.
    - "this year" → year to date; "past year" → the past year.
    - "past N days/weeks" → the last N sessions.
    - A named month or span → explicit start and end dates.
    - If nothing is given, the default is the past 6 months.
- Retrieve the closing prices.
    - If the ticker is unknown, report the error.
    - Retry at most once, only for a transient network error.
- Classify the trend as up, down or flat:
    - Over the whole window.
    - Over the last 20 and last 5 sessions, when there are enough sessions.
- Compute the change over the window, and whether the last close is above or below its 5-, 10-, 20- and 50-session moving averages (where there are enough sessions).
- Output:
    - {{Symbol}} is on an up trend / down trend / is roughly flat, from {{Start Date}} to {{End Date}}.
    - {{Shorter-Window Trends}}, when they disagree with the overall trend.
    - {{Change Over the Window}}
    - {{Last Close vs Moving Averages}}
    - {{Last Close}} {{Currency}} on {{Date}}, noting minor units (e.g. GBp = pence).
    - A short caveat: this is a mechanical read of past closing prices, not a prediction or investment advice.
- If there are too few prices to judge a trend, say so plainly.
- Never fabricate prices, dates or verdicts.
