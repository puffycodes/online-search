# Stock Information

## Requirement

- Use the scripts or agents in this project as much as possible.

## Actions

- Display a text box where the user can enter a stock symbol and submit.
- After submission:
    - Display the company information
        - {{Company Name}}
        - {{Stock Symbol}}
        - {{Company Sector}} {{Company Industry}}
        - {{Market Cap}} {{P/E Ratio}} {{Dividend Yield}}
    - Display the price information
        - {{Current Price}} {{Price Movement}} {{Previous Close}}
        - {{Day Low}} {{Day High}}
            - Show a bar with the {{Day Low}} and {{Day High}} at both ends, and a market to show the {{Current Price}}
        - {{52 Weeks Low}} {{52 Weeks High}}
            - Show a bar with the {{52 Weeks Low}} and {{52 Weeks High}} at both ends, and a marker to show the {{Current Price}}
    - Display the fundamental indicators, grouped
        - Profitability: {{Gross Margin}} {{Operating Margin}} {{Net Margin}} {{Return on Equity}} {{Return on Assets}}
        - Growth: {{Revenue Growth}} {{Earnings Growth}} {{Analyst 5-Year Growth}}
        - Valuation: {{Trailing P/E}} {{Forward P/E}} {{PEG}} {{EV/EBITDA}} {{P/B}} {{P/S}} {{FCF Yield}}
        - Financial health: {{Debt/Equity}} {{Net Debt/EBITDA}} {{Current Ratio}} {{Quick Ratio}}
        - Cash flow: {{Free Cash Flow}} {{Operating Cash Flow}} {{Cash Conversion}}
        - Shareholder returns: {{Dividend Yield}} {{Payout Ratio}}
        - Show "–" for an indicator that is not reported or not meaningful.
    - Display the valuation information
        - Compute the different valuations of the stock.
        - Compute the number of valuations that indicate that the current price is undervalue / fair value / overvalue. A valuation of less than 1% away from the current price is consider "fair value".
        - Display the statistics of the valuations.
            {{Number Undervalue}} {{Number Fair Value}} {{Number Overvalue}}
        - Display the difference valuations in a table.
