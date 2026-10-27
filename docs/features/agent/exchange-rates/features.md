# Exchange Rates

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the exchange_rates.py script to retrieve the rates.

## Actions

- Take the currencies, and optionally an amount and a date or period, from the user's question.
    - Map currency names to ISO codes (dollar → USD, euro → EUR, pound → GBP, yen → JPY, …).
        - A bare "dollar" is USD unless the wording or context names another dollar; say so when assuming USD where another dollar was plausible.
        - When a name could mean several currencies, use the most likely, say which code was used, and name the alternative.
    - "X to Y", "X in Y", "X/Y" and "how many Y per X" all mean base X, quote Y.
- Pick the window from what the user asked, using today's date:
    - "now", "today", "current" or no date → the latest rates.
    - One date ("on 1 March 2020", "last Friday") → that date.
    - A period ("last week", "in March", "this year") → a start date and, if the period has ended, an end date.
        - Over about 3 months: one rate per week. Over about 2 years: one rate per month.
- Retrieve the rates.
    - If a currency code is unknown and was derived from a name, check the mapping once; otherwise report the error.
    - Retry at most once, only for a transient network error.
- Output:
    - A conversion: {{Amount}} {{Base}} = {{Converted}} {{Quote}}, at {{Rate}}, dated {{Date}}; the converted amount in the currency's usual decimals.
    - A rate: 1 {{Base}} = {{Rate}} {{Quote}} on {{Date}}, in the user's framing.
    - Always give each rate's date; for the latest rates, say they are the latest published.
    - A period: the first and last rates, the change between them as a percentage, and the highest and lowest rates with their dates; a table only for about 10 rows or fewer, or when asked.
    - When the user is converting money to spend or send: one line saying these are reference rates and a bank or card adds a spread.
    - Crypto rates are one daily reference value, not a live market price.
    - End with a credit line naming Frankfurter.
- If no rate is returned (before a currency's history, a future date, a retired currency), say so plainly.
- Don't forecast: report the recent movement and say it isn't a prediction.
- Never fabricate rates or dates.
