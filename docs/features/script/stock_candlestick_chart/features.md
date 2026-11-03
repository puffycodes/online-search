# Stock Candlestick Chart

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Get the data through stock_data.py's daily_history() (never from a provider directly), served by price_source.py: EODHD (EODHD_API_KEY), or Alpha Vantage (ALPHAVANTAGE_API_KEY) for Indian tickers, chosen from the Yahoo-notation ticker. Until 2026-10-21 this used Yahoo Finance's chart endpoint, which fails the source audit.
- Show any notes price_source returns (e.g. a free plan returning less history than asked).
- Use yahoo_finance.py's add_window_args() and build_params() for the window, and stock_data.py's label() for the heading.
- Use indicators.py's moving_average() and moving-average crossover functions.
- Use matplotlib to draw the chart.

## Actions

- Run as python3 stock_candlestick_chart.py from the repo root.
- Take:
    - {{Symbol}}: a ticker in Yahoo notation, including the exchange suffix for non-US listings (e.g. AAPL, VOD.L, SAP.DE, RELIANCE.NS). Singapore (.SI), Tokyo (.T) and futures (=F) aren't supported for now and fail before any request.
    - The time window, one of:
        - A range: 5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y or max (default: 6mo).
        - The last N sessions (cannot be combined with a range).
        - A start date, and optionally an end date (default: today), both inclusive, so the same date twice is one day. This replaces a range; combined with the last N sessions, the window starts at the start date and only the final N sessions in it are kept.
    - The candle size: 1d (default), 1wk or 1mo.
    - The image path to write (default: {{Symbol}}_candlestick.png, with any "." in the symbol replaced by "_", e.g. VOD_L_candlestick.png), or open an interactive window instead.
    - Whether to add a volume panel below the prices (default: no).
    - The moving averages to overlay (default: 5, 10, 20 and 50 bars; "none" for no averages).
    - The pair of moving averages whose crossovers are marked (default: 20 and 50; "none" for no markers).
- Retrieve the bars for the window, skipping any bar with a missing open, high, low or close.
- Compute each moving average over the full fetched series, so the averages are right at the chart's left edge.
- Draw the chart:
    - One candle per bar: {{Open}} {{High}} {{Low}} {{Close}}
    - {{Moving Averages}} as lines.
    - An up arrow below the bar where the fast average crosses above the slow one, and a down arrow above the bar where it crosses below.
    - {{Volume}} bars in their own panel, if asked for.
    - A title with {{Symbol}} {{Exchange}} {{Number of Bars}} {{Candle Size}} {{First Date}} → {{Last Date}}
    - {{Currency}} in the price axis label.
- Output: "Wrote {{Image Path}}".
- An unknown ticker, or a window with no data, fails with an error.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure (including matplotlib not being installed) exits with code 1, with "Error: ..." on stderr.
    - An invalid option value exits with code 2, before any network call.
    - A date not in YYYY-MM-DD form exits with code 1 ("invalid date ..."), also before any network call.
