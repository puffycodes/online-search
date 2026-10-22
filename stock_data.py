#!/usr/bin/env python3
"""
Provider-neutral stock data for the stock scripts.

Scripts import this module, not a provider's: each function here returns
plain dicts in a shape no provider dictates, and PROVIDERS routes the call
to the adapter that serves it. Swapping a provider then means changing one
entry in PROVIDERS, not a script. See docs/things-to-explore.md ("Proposed
design") for the full list of functions planned; only analyst_view() is here
so far, served by yahoo_finance.py.

Shared conventions for every result:

- dates are ISO "YYYY-MM-DD" strings (UTC unless a function says otherwise);
- numbers are plain floats or ints, ratios are fractions (0.1 == 10%);
- a field the provider doesn't have is None (a list it doesn't have is []);
- "source" names the provider and "notes" lists anything it flagged.

Fetch failures raise requests.RequestException (or ValueError / KeyError for
a malformed answer), which the scripts turn into an exit-1 error.
"""

import yahoo_finance as yf

# function name -> adapter callable with the same signature
PROVIDERS = {
    "analyst_view": yf.analyst_view,
}


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
