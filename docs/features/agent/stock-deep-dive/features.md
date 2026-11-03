# Stock Deep Dive

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Chain stock_fundamental.py, stock_intrinsic_value.py, stock_analyst_targets.py, stock_holders.py, stock_earnings_calendar.py and stock_price_history.py, with indicators.py for the trend and risk figures, into one report on one company's stock.
    - Read each tool's figures by the same rules as its own agent (stock-fundamental, stock-intrinsic-value, stock-analyst-targets, stock-holders, stock-earnings-calendar, stock-trend, stock-risk).

## Actions

- Take one company named by the user.
    - Resolve it to its Yahoo-notation ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - Decline indices, currency pairs, crypto, commodities and ETFs without running anything, pointing to stock-trend or stock-risk.
    - If unsure of the ticker, say so rather than guess.
    - For several companies, ask which to start with, or run once per company if the user insists.
- Run the fundamentals first, as the ticker check.
    - If Yahoo returns no fundamentals, retry once for a confident ticker; if it still fails, stop and report the error without running the other tools.
- Run the other five tools, saving each result to a scratch directory:
    - Intrinsic value with its default assumptions, or the user's stated ones.
    - Analyst targets over the last 90 days of firm actions.
    - Holders over the last 180 days, trades only.
    - Earnings calendar.
    - A year of prices; skipped for Singapore (.SI) and Tokyo (.T), which the price source doesn't cover for now.
    - A failed tool loses only its own section: retry once if the error looks transient, otherwise report the gap.
- Digest the results into a compact summary: rating changes only from the analyst actions, the top 5 insiders and top 3 holders, and from the prices the year's change, the trend over the year and the last 60 and 20 sessions, the 50- and 200-session averages, the high, annualized volatility and the worst fall with its dates.
- Output:
    - {{Name}} ({{Ticker}}), {{Exchange}}, {{Sector}} / {{Industry}}, {{Price}} {{Currency}}, market cap {{Market Cap}}.
    - At a glance: four to six points that stand out across the sections, each tied to a figure, and where the sections disagree.
    - Business quality: {{Profitability}}, {{Growth}}, {{Balance Sheet}}, {{Cash Flow}}, read against the industry.
    - Valuation: {{DCF Value}} vs {{Price}} with its assumptions, {{Implied Growth}} vs the analyst estimate, {{P/E}}, {{EV/EBITDA}}, {{FCF Yield}}.
    - What analysts think: {{Consensus}}, {{Median / Low / High Target}} and upside, {{Analysts}}, {{Rating Trend}}, {{Upgrades / Downgrades / Initiations}}.
    - Ownership and insiders: {{Insider %}}, {{Institutional %}}, {{Insider Sales and Purchases}} with the most active names, {{Largest Holders}} with report dates.
    - Earnings and dividends: {{Next Report Date}} with estimates, {{Beat / Miss Record}}, {{Dividend Dates}} and {{Last Dividend}}.
    - Price trend and risk: {{Change Over the Year}}, {{Trend}}, {{Shorter-Window Trends}}, {{Price vs 50- and 200-Session Averages}}, {{Distance from High}}, {{Volatility}}, {{Worst Fall}}.
    - Gaps: every section or figure that came back unavailable, and why.
    - A caveat: one point-in-time snapshot from Yahoo Finance and EODHD / Alpha Vantage; the models and trend fits are mechanical and assumption-sensitive; analyst targets are opinions; not a forecast or investment advice.
- Never give a buy, sell or hold view, and never fabricate figures, dates, names or verdicts.
