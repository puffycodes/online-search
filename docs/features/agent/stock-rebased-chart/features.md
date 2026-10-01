# Stock Rebased Comparison Chart

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_rebased_chart.py script to draw the chart.

## Actions

- Take one or more stocks named by the user.
    - Resolve each company to its Yahoo Finance ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - If unsure of a ticker, say so rather than guess.
    - Stocks from different exchanges and currencies can be mixed.
    - Put the stock the user treats as the anchor first.
- Pick the time window from what the user asked:
    - "last N days/weeks" → the last N sessions.
    - "past 3 months", "this year", "last 5 years" → the matching range (5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y, max).
    - A named month or span ("in August", "since June") → explicit start and end dates.
    - If nothing is given, the default is the past 6 months.
- Pick the base date, where every stock is rescaled to read 100:
    - By default, the first date of the window.
    - If the user names a reference date inside a longer window, use that date (a trading day; if the market was closed, the nearest earlier trading day).
- Draw the chart to an image file in the system temp directory, never in the project.
    - Read the image back to check that it rendered.
    - If a stock has no price on the base date or fails to fetch, it is left off the chart; say which and why.
        - If the base date was the problem, retry once with the nearest earlier weekday.
    - If no stock can be drawn, report the error.
    - Retry at most once, only for a transient network error.
- Output:
    - Two or three sentences: {{Stocks Plotted}}, {{Period}}, {{Base Date}}, and a read of the chart:
        - {{Best Performer}} (furthest above 100) and {{Worst Performer}} (furthest below 100)
        - Roughly how far apart they end, read off the chart's axis.
        - Any notable crossover or divergence.
    - {{Stocks Dropped}}, with the reason, if any.
    - Chart: {{Absolute Path to the Image}}, on its own line at the end.
- Never fabricate prices, percentages, dates or trends.
