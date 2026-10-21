# Stock Rebased Comparison Chart

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_rebased_chart.py script to draw the chart.

## Actions

- Take one or more stocks, market indices, currency pairs, or cryptocurrencies named by the user.
    - For a stock, resolve the company to its Yahoo-notation ticker, adding the exchange suffix for non-US listings (e.g. .L, .DE, .PA, .TO, .AX, .NS, .HK); the tool gets the data from EODHD, or Alpha Vantage for Indian stocks.
    - Singapore (.SI) and Tokyo (.T) listings and futures (=F) aren't supported for now: say so instead of running the tool.
    - For anything else, use Yahoo's own symbol:
        - Index: ^ prefix (e.g. ^GSPC S&P 500, ^IXIC Nasdaq Composite, ^HSI Hang Seng); ^FTSE returns no data, so report an index with no data as unavailable.
        - Currency pair: BASEQUOTE=X (e.g. EURUSD=X); for USD-based pairs the base is dropped (JPY=X is USD/JPY). The price is the quote currency per one unit of the base.
        - Cryptocurrency: COIN-CURRENCY (e.g. BTC-USD).
    - If unsure of a ticker, say so rather than guess.
    - Instruments from different exchanges, currencies and asset classes can be mixed.
    - Put the stock the user treats as the anchor first.
- When the user compares stocks against a market or index ("vs the S&P 500", "did they beat the market?"), draw that index as the benchmark rather than as another stock.
    - "The market" with no index named → the main index of the stocks' own exchange (e.g. ^GSPC US, ^HSI Hong Kong); ^FTSE returns no data, so for London say so and offer ^GSPC.
    - Indices compared with each other, or no market mentioned → no benchmark.
- Pick the time window from what the user asked:
    - "last N days/weeks" → the last N sessions.
    - "past 3 months", "this year", "last 5 years" → the matching range (5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y, max).
    - A named month or span ("in August", "since June") → explicit start and end dates.
    - If nothing is given, the default is the past 6 months.
- Pick the base date, where every stock is rescaled to read 100:
    - By default, the first date of the window.
    - If the user names a reference date inside a longer window, use that date (a trading day; if the market was closed, the nearest earlier trading day).
    - Crypto trades every day; with crypto in the mix, pick a weekday the other markets also traded on.
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
        - With a benchmark: which stocks ended above it and which below, roughly by how much; or that it was dropped.
    - {{Stocks Dropped}}, with the reason, if any.
    - Chart: {{Absolute Path to the Image}}, on its own line at the end.
- Never fabricate prices, percentages, dates or trends.
