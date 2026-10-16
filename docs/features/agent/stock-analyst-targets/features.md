# Stock Analyst Targets

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_analyst_targets.py script to retrieve the analyst targets, ratings and recent firm-level actions.

## Actions

- Take one or more stocks named by the user.
    - Resolve each company to its Yahoo Finance ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - If unsure of the ticker, say so rather than guess.
    - Analysts cover company stocks only; for an ETF, index, currency or commodity, say so instead of retrieving anything.
- Retrieve the analyst targets and ratings, once per ticker.
    - When the user names a period for recent analyst actions, retrieve that many {{Days}}; otherwise the last 90.
    - `no fundamentals in response` can mean an unknown ticker or a temporary Yahoo glitch: for a ticker you're confident of, retry once before reporting it; for one you guessed, say it may be wrong.
    - If the ticker is unknown or has no analyst coverage, report the error.
    - Retry at most once in total: for that error, or a transient network error.
- Output:
    - {{Consensus Rating}}, {{Median Target}} and {{Mean Target}} with the {{Upside}} from {{Price}}, and the {{Number of Analysts}}.
    - {{Low Target}} to {{High Target}}; a wide spread means analysts disagree.
    - Any shift in the buy / hold / sell counts over the months shown, or that sentiment is unchanged.
    - Recent analyst actions: each upgrade, downgrade and initiation with {{Firm}} {{Date}} {{From Grade}} {{To Grade}}, then a summary of target raises and cuts; plain reiterations only when asked.
        - Lead with these when the user asked about upgrades or downgrades.
        - With none, say Yahoo lists none in the window (Yahoo has them for US listings only).
    - For several companies, a table: {{Symbol}} {{Price}} {{Median Target}} {{Upside}} {{Consensus}} {{Analysts}}
    - Targets in the trading {{Currency}}, noting minor units (e.g. GBp = pence).
    - A short caveat: other people's opinions, aggregated by Yahoo Finance; price targets are often wrong and are not a forecast or investment advice.
- Never add a buy or sell view of your own.
- Never fabricate targets, ratings, counts or firm actions.
