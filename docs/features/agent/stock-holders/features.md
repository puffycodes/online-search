# Stock Holders

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_holders.py script to retrieve the ownership, insider transactions and top holders.

## Actions

- Take one or more stocks named by the user.
    - Resolve each company to its Yahoo Finance ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - If unsure of the ticker, say so rather than guess.
    - Only company stocks have holders; for an ETF, index, currency or commodity, say so instead of retrieving anything.
- Retrieve the ownership data, once per ticker.
    - When the user names a period for insider activity, retrieve that many {{Days}} ("this year" = today's day of the year); for vague words ("lately", "recently") or no period, the last 180, and say which window was used.
    - When the question is only about insider buying and selling, retrieve trades only (sales, purchases, option exercises); the summary still counts everything.
    - `no fundamentals in response` can mean an unknown ticker or a temporary Yahoo glitch: for a ticker you're confident of, retry once before reporting it; for one you guessed, say it may be wrong.
    - If the ticker is unknown or has no ownership data, report the error.
    - Retry at most once in total: for that error, or a transient network error.
- Output:
    - What the user asked first: for insider activity, {{Number of Sales}} and {{Number of Purchases}} with {{Shares}} and {{Value}}, and the most active {{Insider}} with their {{Role}} (from the per-insider totals, not added up by hand); for ownership, {{Insiders %}}, {{Institutions %}} and the largest {{Holders}}.
    - Holder disclosures are stake notices, from banks and funds or, outside the US, directors' own holding notices; never trades.
    - For non-US listings, give trade prices and values in US dollars (the transaction currency) and fund values in the quote currency (e.g. pence for London); never mix the two.
    - A holder's value is at today's price, not at its report date; the report date applies to the shares and %.
    - Keep awards, option exercises, gifts and company buybacks apart from insider buying and selling; don't treat insider selling as a signal on the stock.
    - For non-US listings: say most transactions are company buybacks or holder disclosures, report real director trades separately, and note prices may not be in the quote currency; don't show the institution list.
    - The {{Report Date}} of the holder lists; they are periodic filings, not current.
    - For several companies, a table: {{Symbol}} {{Insiders %}} {{Institutions %}} {{Sales vs Purchases}} {{Largest Holder}}
    - A short caveat: as reported to and aggregated by Yahoo Finance, can lag, not investment advice.
- Never fabricate holders, transactions, percentages or values.
