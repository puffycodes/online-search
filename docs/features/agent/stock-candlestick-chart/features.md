# Stock Candlestick Chart

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_candlestick_chart.py script to draw the chart.

## Actions

- Take a stock named by the user.
    - Resolve the company to its Yahoo Finance ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - If unsure of the ticker, say so rather than guess.
- Pick the time window from what the user asked:
    - "last N days/weeks" → the last N sessions.
    - "past 3 months", "this year", "last 5 years" → the matching range (5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y, max).
    - A named month or span ("in August", "since June") → explicit start and end dates.
    - If nothing is given, the default is the past 6 months.
- Pick the candle size: daily by default; weekly when asked or for 2 years or more; monthly when asked.
- Add a volume panel when the user mentions volume or the horizon is long.
- Moving averages:
    - The defaults are 5, 10, 20 and 50 sessions; use the ones the user names, or none if asked.
    - Mark the crossovers of the 20- and 50-session averages by default, or the pair the user names, or none if asked.
- Draw the chart to an image file in the system temp directory, never in the project.
    - Read the image back to check that it rendered.
    - If the ticker is unknown or the dates are invalid, report the error.
    - Retry at most once, only for a transient network error.
- Output:
    - One or two sentences: {{Symbol}} {{Exchange}}, {{Period}} {{Candle Size}}, and a brief read of the chart ({{Overall Trend}}, {{Notable Move}}, {{Current Price}} {{Currency}}).
    - Chart: {{Absolute Path to the Image}}, on its own line at the end.
- If no data is returned, say so plainly instead of drawing a chart.
- Never fabricate prices, dates or trends.
