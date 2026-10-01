# Top Volume Stocks

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the market_top_volume.py script to retrieve the top movers.

## Actions

- Take a market named by the user.
    - Map the user's wording to a supported market (e.g. "London" → UK, "DAX" → Germany, "Toronto" → Canada).
    - If no market is given, the default is the US.
    - If the market isn't supported, list the supported markets instead of guessing.
- Take the measure from what the user asked:
    - Highest trading volume (the default), biggest gainers, or biggest losers.
- Take how many stocks to list.
    - The default is 10; use 1 when the user wants only the top stock.
- Retrieve the top movers.
    - Retry at most once, only for a transient network error.
- Output:
    - The top stock first: {{Symbol}} {{Company Name}}, with the measure's own figure first, then {{Volume}} {{Price}} {{Currency}} {{Percent Change}}.
    - The rest as a numbered list, if asked for.
    - Note that figures are from the latest session (intraday if the market is open).
    - Note minor units (e.g. GBp = pence), and that small, obscure stocks can dominate the gainers and losers lists.
- If no stocks are returned, say so plainly.
- Never fabricate tickers or figures.
