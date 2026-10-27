# Exchange Rates

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use Frankfurter's v2 rates API (documented; no key, no quotas), checked in docs/source-audit.md.
- Ask only for Frankfurter's blended rates, never a single provider's (those fall under that provider's own terms).
- Use daily_prices.py's parse_date() and resolve_window(), and cli_utils.py's raise_for_status() and die().

## Actions

- Run as python3 exchange_rates.py from the repo root.
- Take:
    - {{Base}}: the base currency, an ISO code (any case).
    - {{Quotes}}: optionally, the currencies to convert into; none means every currency.
    - {{Amount}}: optionally, an amount of the base currency to convert (default 1; must be above 0).
    - The time window, one of:
        - A date: the rates on that date.
        - A start date, and optionally an end date (default: today), both inclusive: the rates over that range, daily, or one per week or month.
        - Neither: the latest rates.
- Retrieve the rates.
    - Skip any record without a date, currency or rate.
    - Convert {{Amount}} at each rate.
- Output:
    - For the latest rates or one date: {{Base}} exchange rates {{Window}}, then one line per currency in code order: {{Date}} {{Amount}} {{Base}} = {{Converted}} {{Quote}}, with the rate when the amount isn't 1. Each line keeps its own date, since the latest rates of different currencies can come from different days.
    - For a range: {{Base}} exchange rates {{Window}}, then a table with one row per date and one column per currency, showing the converted amount ("-" where a currency has no rate that day).
    - Converted amounts to 4 decimal places, or to 4 significant digits below 0.01.
    - A last line naming the source: Frankfurter's blended rates from central banks and official sources.
    - With --json: {base, quotes, amount, date, start, end, group, source, rates: [{date, quote, rate, converted}]}, the rates sorted by date then currency.
- No rates for the date or range is not an error: say "No {{Base}} rates found for {{Quotes}} {{Window}}." (or return an empty rates list) and exit normally.
- An unknown currency fails with Frankfurter's message ("HTTP 422: invalid currency: ZZZ").
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call: an amount of 0 or below or not a number, a date together with a start or end date, a grouping without a start date, or a grouping other than week or month.
    - A date not in YYYY-MM-DD form, an end date without a start date, or an end before the start exits with code 1, before any network call.
