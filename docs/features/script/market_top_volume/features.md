# Market Top Movers

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use Yahoo Finance's screener endpoints (unofficial; no API key).
    - US markets use the keyless predefined screeners; other markets use the generic screener, which needs a cookie and crumb.
- Use yahoo_finance.py's HEADERS, REQUEST_TIMEOUT and fetch_crumb().
- Keep get_movers() importable, for stock_tech_buzz_agent.py.

## Actions

- Run as python3 market_top_volume.py from the repo root.
- Take:
    - The market (default: us). One of: us, nyse, nasdaq, amex, uk/lse, germany/xetra, france/euronext-paris, netherlands, spain, italy, switzerland, sweden, canada/tsx, australia/asx, india/nse/bse, hongkong/hkex, japan, singapore, newzealand, brazil.
    - The measure (default: volume): volume (most shares traded), gainers (biggest % rise) or losers (biggest % fall).
    - How many stocks to return (default: 10).
- Retrieve the stocks for the market, sorted by the measure.
    - Keep only stocks listed on the market's own exchange(s), where the market maps to specific exchanges.
    - For gainers and losers, drop stocks that traded fewer than 50,000 shares.
- Output, one entry per stock, with the measure's own figure first:
    - {{Rank}} {{Symbol}} {{Company Name}} {{Exchange}}
    - {{Volume}} {{Price}} {{Currency}} {{Percent Change}}
    - With --json: an array of {rank, symbol, name, exchange, volume, price, change_percent, currency}.
- If no stocks are returned, say so.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
