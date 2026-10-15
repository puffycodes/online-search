# Stock Candlestick Chart

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_candlestick_chart.py script to draw the chart.

## Actions

- Take a stock, market index, currency pair, cryptocurrency or futures contract / commodity named by the user.
    - For a stock, resolve the company to its Yahoo Finance ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - For anything else, use Yahoo's own symbol:
        - Index: ^ prefix (e.g. ^GSPC S&P 500, ^FTSE FTSE 100, ^N225 Nikkei 225).
        - Currency pair: BASEQUOTE=X (e.g. EURUSD=X); for USD-based pairs the base is dropped (JPY=X is USD/JPY). The price is the quote currency per one unit of the base.
        - Cryptocurrency: COIN-CURRENCY (e.g. BTC-USD).
        - Futures / commodity: =F suffix, a continuous front-month series (e.g. GC=F gold, CL=F crude oil).
    - If unsure of the ticker, say so rather than guess.
- Pick the time window from what the user asked:
    - "last N days/weeks" → the last N sessions.
    - "past 3 months", "this year", "last 5 years" → the matching range (5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y, max).
    - A named month or span ("in August", "since June") → explicit start and end dates.
    - If nothing is given, the default is the past 6 months.
- Pick the candle size: daily by default; weekly when asked or for 2 years or more; monthly when asked.
- Add a volume panel when the user mentions volume or the horizon is long, but never for a currency pair (it has no volume).
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
