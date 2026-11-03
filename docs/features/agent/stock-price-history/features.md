# Stock Price History

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_price_history.py script to retrieve the daily prices.

## Actions

- Take a stock, market index, currency pair, or cryptocurrency named by the user.
    - For a stock, resolve the company to its Yahoo-notation ticker, adding the exchange suffix for non-US listings (e.g. .L, .DE, .PA, .TO, .AX, .NS, .HK); the tool gets the data from EODHD, or Alpha Vantage for Indian stocks.
    - Singapore (.SI) and Tokyo (.T) listings and futures (=F) aren't supported for now: say so instead of running the tool.
    - For anything else, use Yahoo's own symbol:
        - Index: ^ prefix (e.g. ^GSPC S&P 500, ^IXIC Nasdaq Composite, ^HSI Hang Seng); ^FTSE returns no data, so report an index with no data as unavailable.
        - Currency pair: BASEQUOTE=X (e.g. EURUSD=X); for USD-based pairs the base is dropped (JPY=X is USD/JPY). The price is the quote currency per one unit of the base.
        - Cryptocurrency: COIN-CURRENCY (e.g. BTC-USD).
    - If unsure of the ticker, say so rather than guess.
- Pick the time window from what the user asked:
    - "yesterday", "last close", "previous session" → the last 2 sessions (report the most recent).
    - "last week", "past N days" → the last N sessions.
    - A specific date ("on 3 March", "last Friday") → that date as both start and end.
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
    - Currency pairs have no volume; leave it out.
    - Crypto and currency pairs trade around the clock, so the last price may be today's still-moving bar; say so if it is today's date.
- If no prices are returned, say so plainly.
- Never fabricate prices or dates.
