# Stock Closing Price

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_close_history.py script to retrieve the daily prices.

## Actions

- Take a stock named by the user.
    - Resolve the company to its Yahoo Finance ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - If unsure of the ticker, say so rather than guess.
- Pick the time window from what the user asked:
    - "yesterday", "last close", "previous session" → the last 2 sessions (report the most recent).
    - "last week", "past N days" → the last N sessions.
    - A named month or span ("in August", "since June") → explicit start and end dates.
    - A longer horizon ("this year", "past 5 years") → the matching range (5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y, max).
    - If nothing is given, the default is the past month.
- Retrieve the daily prices. Only settled sessions are included.
    - If the ticker is unknown, report the error.
    - Retry at most once, only for a transient network error.
- Output:
    - For a single price: {{Symbol}} closed at {{Close}} {{Currency}} on {{Date}}
    - For open, high, low or "OHLC": {{Open}} {{High}} {{Low}} {{Close}} for the session(s) asked about.
    - For a series, a table with one row per session:
        - {{Date}} {{Open}} {{High}} {{Low}} {{Close}} {{Volume}}
        - Add {{Adjusted Close}} only when it differs from {{Close}} (a dividend or split fell in the window).
    - State the {{Currency}}, and note minor units (e.g. GBp = pence).
- If no prices are returned, say so plainly.
- Never fabricate prices or dates.
