# Stock Intrinsic Value

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the stock_intrinsic_value.py script to compute the valuations.

## Actions

- Take a stock named by the user.
    - Resolve the company to its Yahoo Finance ticker, adding the exchange suffix for non-US listings (e.g. .L, .SI, .DE, .PA, .TO, .AX, .NS, .HK, .T).
    - If unsure of the ticker, say so rather than guess.
- Pick the assumptions:
    - By default, let the script derive them (discount rate from the stock's beta, growth from the analyst estimate, 2.5% terminal growth, 10 years).
    - Use any discount rate, growth, terminal growth, horizon, P/E, EV/EBITDA, P/S or CAPM input the user states.
- If the user asks whether the stock is over- or undervalued, or wants a considered fair value, run conservative, base and optimistic scenarios by varying growth and discount rate.
- Compute the valuations.
    - If the ticker is unknown, report the error.
    - Retry at most once, only for a transient network error.
- Output:
    - The headline: {{DCF Value}} (or the {{DCF Range}} across scenarios) against {{Current Price}}, with the {{Discount Rate}} {{Growth}} {{Years}} used.
    - The reverse DCF: {{Implied Growth}} needed to justify the price, against {{Analyst Growth}}.
    - The other independent estimates, each with {{Value per Share}} and whether the price is above or below it:
        - The dividend discount model only for real dividend payers.
        - Multiple-based estimates only when the user supplied the multiple; otherwise say they just echo the current multiple.
    - {{Missing Estimates}}, with the input that was missing.
    - A short caveat: these are mechanical model outputs, sensitive to the assumptions and built on one snapshot of Yahoo fundamentals, not investment advice.
- Never fabricate values, assumptions or fundamentals.
