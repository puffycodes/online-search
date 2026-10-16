# Stock Holders

## Requirement

- Reuse the shared modules and scripts in this project (rather than copying their logic) as much as possible.
    - Use yahoo_finance.py's fetch_quote_summary() to retrieve Yahoo Finance's quoteSummary data, and its summary_num() / summary_text() to read it.

## Actions

- Run as python3 stock_holders.py from the repo root.
- Take:
    - {{Symbol}}: a ticker in Yahoo notation, including the exchange suffix for non-US listings (e.g. AAPL, VOD.L, D05.SI, SAP.DE).
    - --days {{Days}} (default 180, a positive integer): how far back to list insider transactions.
    - --trades-only: list only sales, purchases and option exercises; the summary still counts every transaction.
- Retrieve the stock's ownership breakdown, insider transactions, and top fund and institutional holders.
- Report:
    - Ownership: {{Insiders %}} {{Institutions %}} {{Institutions % of Float}} {{Number of Institutions}}
    - Insider transactions in the last {{Days}} days, newest first: {{Date}} (UTC) {{Name}} {{Role}} {{Kind}} {{Shares}} {{Price}} (a single price or a low-high range, from the description) {{Value}} {{Direct or Indirect}}
        - {{Kind}} is decided from the description: sale, purchase, option exercise, award, gift, buyback or other. With no description, it is a buyback when the company itself filed it, a holder disclosure when no role is given, and unspecified otherwise.
        - Yahoo's zero placeholders for value and price are left blank.
    - Insider summary: {{Sales}} and {{Purchases}}, each with count, shares and value; every other kind only counted, never added to sales or purchases.
    - Per insider, for everyone with a sale or purchase, most value traded first: {{Name}} {{Role}} {{Sales}} {{Purchases}}, each with count, shares and value (the first 10 in the text report).
    - Top funds: {{Holder}} {{% Held}} {{Change}} {{Shares}} {{Value}} {{Report Date}}
    - Top institutions, in the same form, for US listings only (a symbol without an exchange suffix). For non-US listings, say they are not shown, because Yahoo lists only small US filers for them.
- Don't use Yahoo's 6-month net share purchase summary: it counts stock awards as buys.
- Output:
    - {{Company Name}} {{Symbol}} {{Exchange}} {{Currency}}
    - One section per part above; a missing part says Yahoo has no data for it.
    - Notes that holder lists are periodic filings, and, for non-US listings, that many transactions are buybacks or holder disclosures (including directors' holding notices) and that their insider-trade prices and values appear to be in USD, not the quote currency. A holder's value is its reported shares at today's price, in the quote currency.
    - {{Transaction Currency}}: the quote currency for US listings, USD for non-US listings (Yahoo doesn't label it; non-US trade prices match the local price converted to US dollars).
    - With --json: {symbol, name, exchange, currency, us_listing, transaction_currency, ownership, days, trades_only, insider_summary: {sales, purchases, other_counts, by_insider}, transactions, top_funds, top_institutions}; top_institutions is null for non-US listings.
- An unknown ticker fails with an error. So does a symbol with no ownership breakdown, no transactions (counting any left out by --trades-only) and no holders (an ETF, index, currency or future).
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option exits with code 2, before any network call.
