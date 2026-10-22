#!/usr/bin/env python3
"""
Provider-neutral stock data for the stock scripts.

Scripts import this module, not a provider's: each function here returns
plain dicts in a shape no provider dictates, and PROVIDERS routes the call
to the adapter that serves it. Swapping a provider then means changing one
entry in PROVIDERS, not a script. See docs/things-to-explore.md ("Proposed
design") for the full list of functions planned. Every stock script except the
price scripts (which use price_source.py), and the stock web app, get their
data here now: analyst_view(), earnings_view(), holders_view(),
fundamentals_view(), top_movers() and quote(), all served by yahoo_finance.py.

Shared conventions for every result:

- dates are ISO "YYYY-MM-DD" strings (UTC unless a function says otherwise);
- numbers are plain floats or ints, ratios are fractions (0.1 == 10%), except
  a field whose name ends in "_percent", which is in percent (4.5 == 4.5%);
- a field the provider doesn't have is None (a list it doesn't have is []);
- "source" names the provider and "notes" lists anything it flagged.

Fetch failures raise requests.RequestException (or ValueError / KeyError for
a malformed answer), which the scripts turn into an exit-1 error.
"""

import yahoo_finance as yf

# function name -> adapter callable with the same signature
PROVIDERS = {
    "analyst_view": yf.analyst_view,
    "earnings_view": yf.earnings_view,
    "holders_view": yf.holders_view,
    "fundamentals_view": yf.fundamentals_view,
    "top_movers": yf.top_movers,
    "mover_markets": yf.mover_markets,
    "quote": yf.quote,
}

# The rankings top_movers() offers.
MOVER_METRICS = ("volume", "gainers", "losers")


def analyst_view(symbol, days):
    """Analyst opinion on ``symbol``: price targets, consensus, rating trend and
    firm-level actions over the last ``days`` days (functions 10-12, with the
    profile and price they need).

    Returns::

        {source, notes, name, exchange, currency, price,
         analysts,                          # number with a price target
         targets: {low, median, mean, high},
         recommendation: {key, mean},       # key e.g. "buy", "strong_buy"; mean on 1-5
         trend: [{period, strong_buy, buy, hold, sell, strong_sell}],
                                            # period "0m", "-1m", ... newest first
         actions: [{date, firm, action, from_grade, to_grade,
                    target_action, target, prior_target}]}
                                            # newest first; action is upgrade /
                                            # downgrade / initiate / reiterate /
                                            # maintain; target_action is raised /
                                            # lowered / maintained / announced /
                                            # adjusted or None
    """
    return PROVIDERS["analyst_view"](symbol, days)


def earnings_view(symbol):
    """``symbol``'s earnings calendar: the next report with its estimates, the
    dividend dates and the recent quarters' EPS (functions 7-9, with the
    profile they need).

    Returns::

        {source, notes, name, exchange, currency,
         reporting_currency,                # of EPS and revenue; None if unknown
         next_earnings: {date, date_end, datetime_utc, is_estimate,
                         eps_estimate: {low, average, high} | None,
                         revenue_estimate: {low, average, high} | None} | None,
                                            # date_end > date for an estimated
                                            # window; datetime_utc "YYYY-MM-DDTHH:MMZ"
         dividend: {ex_dividend_date, payment_date, last_amount,
                    last_amount_date, amount_currency} | None,
                                            # the latest known dates, which can be
                                            # past; amount_currency None if unknown
         earnings_history: [{quarter_end, fiscal_quarter, reported_date,
                             eps_estimate, eps_actual, surprise_pct, currency}]}
                                            # oldest first; surprise_pct a fraction
    """
    return PROVIDERS["earnings_view"](symbol)


def holders_view(symbol, days):
    """Who owns ``symbol`` and what its insiders did in the last ``days`` days:
    the ownership split, insider transactions and the top holders (functions
    13-15, with the profile they need).

    Returns::

        {source, notes, name, exchange, currency,
         us_listing,                        # no exchange suffix on the ticker
         transaction_currency,              # of transaction prices and values;
                                            # None if unknown
         ownership: {insiders_pct, institutions_pct, institutions_float_pct,
                     institutions_count},   # fractions, and an int count
         transactions: [{date, name, relation, kind, text, shares, value,
                         price_low, price_high, ownership}],
                                            # newest first; kind is sale / purchase
                                            # / option_exercise / award / gift /
                                            # buyback / holder_disclosure / other /
                                            # unspecified; text the provider's own
                                            # description; ownership direct /
                                            # indirect / "direct and indirect"
         top_funds: [{name, pct_held, shares, value, pct_change, report_date}],
         top_institutions: [same] | None}   # None where the provider's list
                                            # isn't meaningful
    """
    return PROVIDERS["holders_view"](symbol, days)


def fundamentals_view(symbol):
    """``symbol``'s company figures: profile, size, results, ratios, multiples
    and analysts' growth estimates (functions 4-6), as the provider reports them.
    Trailing-12-month amounts are in the reporting currency as the provider
    gives them; per-share figures and the price in the quote currency.

    Returns::

        {source, notes, name, exchange, currency, sector, industry,
         price, market_cap, shares_outstanding,
         free_cash_flow, operating_cash_flow, ebitda, revenue, net_income,
         total_debt, total_cash,
         eps_ttm, eps_forward, book_value_per_share, beta,
         trailing_pe, forward_pe, price_to_sales, price_to_book,
         enterprise_value, ev_to_ebitda,
         gross_margin, operating_margin, net_margin,      # fractions; gross_margin
         return_on_equity, return_on_assets,             # None if not applicable
         revenue_growth, earnings_growth,                # YoY, latest quarter
         debt_to_equity, current_ratio, quick_ratio,     # plain ratios (1.5 == 1.5x)
         dividend_per_share,                             # forward, in the quote's
                                                         # unit; None for a non-payer
         payout_ratio,
         analyst_growth_1y, analyst_growth_5y}           # fractions
    """
    return PROVIDERS["fundamentals_view"](symbol)


def top_movers(market, metric, limit):
    """The top ``limit`` stocks on ``market`` (one of mover_markets()) by
    ``metric`` (one of MOVER_METRICS): most shares traded, biggest rise or
    biggest fall in the latest session (function 3).

    Returns::

        {source, notes,
         movers: [{symbol, name, exchange, volume, price, change_percent,
                   currency}]}          # best first; change_percent in percent
    """
    return PROVIDERS["top_movers"](market, metric, limit)


def mover_markets():
    """The market names top_movers() accepts from its provider."""
    return PROVIDERS["mover_markets"]()


def quote(symbol):
    """``symbol``'s latest price and session (function 2).

    Returns::

        {source, notes, name, symbol, exchange, currency,
         price,                             # None if the provider has none
         price_time,                        # "YYYY-MM-DD HH:MM[ TZ]" local, or None
         session_date,                      # the latest session, exchange-local
         session_high, session_low,
         previous_close,                    # the last close before that session
         week52_low, week52_high}
    """
    return PROVIDERS["quote"](symbol)
