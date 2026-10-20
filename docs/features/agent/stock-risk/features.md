# Stock Risk

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_risk.py script to measure volatility, drawdowns and correlations.

## Actions

- Take one or more stocks, market indices, currency pairs, cryptocurrencies or futures contracts / commodities named by the user.
    - For a stock, resolve the company to its Yahoo Finance ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - For anything else, use Yahoo's own symbol:
        - Index: ^ prefix (e.g. ^GSPC S&P 500, ^FTSE FTSE 100, ^N225 Nikkei 225).
        - Currency pair: BASEQUOTE=X (e.g. EURUSD=X); for USD-based pairs the base is dropped (JPY=X is USD/JPY).
        - Cryptocurrency: COIN-CURRENCY (e.g. BTC-USD).
        - Futures / commodity: =F suffix, a continuous front-month series (e.g. GC=F gold, CL=F crude oil).
    - If unsure of the ticker, say so rather than guess.
- Add a benchmark when the user compares against a market, or asks how risky a single stock is and a market reference helps (the stock's home index, e.g. ^GSPC for US, ^FTSE for London). For a comparison of named instruments, list them all as symbols, without a benchmark.
- Pick the time window from what the user asked:
    - "lately", "recently", "this quarter" → the past 3 months.
    - "this year" → year to date; "past year" → the past year; "past 5 years" → the past 5 years.
    - "past N days/weeks" → the last N sessions.
    - A named month or span → explicit start and end dates.
    - If nothing is given, the default is the past year.
    - Say so when a very short window (under about a month) makes the figures noisy.
- Retrieve the figures.
    - If every ticker is unknown, report the error.
    - If only some were skipped, report the rest and name the skipped ones with their reason, without rerunning.
    - Retry at most once, only for a transient network error.
- Output:
    - The answer to the question asked first (e.g. which is riskier, whether it has recovered, whether they are correlated), over {{Start Date}} to {{End Date}}.
    - {{Volatility}} as a yearly percentage, with a loose sense of scale, and compared with the benchmark when there is one.
    - {{Worst Fall}} with its peak and trough dates and whether and when it recovered; {{Distance From High}} when relevant.
    - {{Correlation}} for each pair, with a plain reading (moved closely together, somewhat together, little consistent link, tended to move opposite); mention the shared sessions when they are far fewer than each series' own.
    - For three or more symbols, a table of change, volatility, worst fall and recovery, with the correlations below it.
    - Note when the price basis is the raw close over a long window, minor-unit currencies (e.g. GBp = pence), and that the last session may be today's still-moving bar for crypto, currency pairs and futures.
    - A short caveat: the figures describe past behaviour over the window, don't predict future swings, correlation isn't causation, and none of it is investment advice. Never call anything safe or a good buy.
- Never fabricate figures, dates or verdicts.
