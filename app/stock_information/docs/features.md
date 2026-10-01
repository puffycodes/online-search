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
            - SHow a bar with the {{Day Low}} and {{Day High}} at both ends, and a market to show the {{Current Price}}
        - {{52 Weeks Low}} {{52 Weeks High}}
            - Show a bar with the {{52 Weeks Low}} and {{52 Weeks High}} at both ends, and a marker to show the {{Current Price}}
    - Display the valuation information
        - Compute the different valuations of the stock.
        - Compute the number of valuations that are above / same / below the current price. A valuation of less than 1% away from the current price is consider "same".
        - Display the statistics of the valuations.
            {{Number Below}} {{Number Same}} {{Number Above}}
        - Display the difference valuations in a table.
