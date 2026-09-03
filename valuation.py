#!/usr/bin/env python3
"""
Small, dependency-free intrinsic-value estimators for a single stock.

Intrinsic value is never one number - it is whatever a model returns for the
assumptions you feed it. These functions just make the arithmetic of the
common methods explicit and composable:

- ``gordon_growth_value``   - a cash flow growing forever at a constant rate
                              (perpetuity / constant-growth DDM / DCF terminal
                              value).
- ``discounted_cash_flow``  - a two-stage DCF: an explicit free-cash-flow
                              forecast plus a Gordon-growth terminal value,
                              discounted to today.
- ``multiple_value`` /      - apply a "fair" valuation multiple to a
  ``ev_multiple_value``       per-share metric (P/E, P/S, P/B) or to a whole
                              enterprise metric (EV/EBITDA, EV/Sales).
- ``equity_from_enterprise`` - bridge an enterprise value to equity value per
                              share (subtract net debt, divide by shares).
- ``implied_growth_rate``   - reverse DCF: the forecast-stage growth rate the
                              current price implies, other assumptions held.

Rates are fractions, not percents (0.09 == 9%). Cash-flow and value inputs are
in whatever currency unit you pass; per-share outputs are in that unit divided
by the share count. Not a CLI - this module is imported, not run.
"""


def _growth_path(growth, years):
    """Normalise ``growth`` to a list of per-year rates.

    ``growth`` is either a single rate (repeated ``years`` times) or an
    iterable of per-year rates (used as-is; ``years`` is then ignored).
    """
    try:
        path = [float(g) for g in growth]
    except TypeError:
        if years is None:
            raise ValueError("years is required when growth is a single rate")
        if years < 1:
            raise ValueError("years must be a positive integer")
        path = [float(growth)] * int(years)
    if not path:
        raise ValueError("need at least one forecast year")
    return path


def gordon_growth_value(cash_flow, discount_rate, growth):
    """Present value of a cash flow growing forever at a constant rate.

    This one formula is the Gordon growth model, a constant-growth dividend
    discount model, and the terminal value at the end of a DCF forecast.

    cash_flow     : the cash flow expected **one year from now** (already
                    grown one period - D1 in the textbook formula).
    discount_rate : annual discount rate / required return, as a fraction.
    growth        : perpetual growth rate as a fraction; must be strictly
                    below ``discount_rate`` or the value is infinite.

    Returns ``cash_flow / (discount_rate - growth)``.

    >>> gordon_growth_value(5.0, 0.08, 0.03)
    100.0
    """
    if discount_rate <= growth:
        raise ValueError("discount_rate must exceed growth for a finite value")
    return cash_flow / (discount_rate - growth)


def equity_from_enterprise(enterprise_value, net_debt=0.0, shares=None):
    """Bridge an enterprise value to equity value, optionally per share.

    enterprise_value : value of the whole business (debt + equity funded).
    net_debt         : total debt minus cash & equivalents. Positive is net
                       debt and is subtracted; a negative value (net cash) is
                       added back.
    shares           : shares outstanding. If given, the result is per share;
                       otherwise it is the total equity value.

    >>> equity_from_enterprise(1_680_000, net_debt=-50_000, shares=15_000)
    115.33333333333333
    """
    equity_value = enterprise_value - net_debt
    if shares is None:
        return equity_value
    if shares <= 0:
        raise ValueError("shares must be positive")
    return equity_value / shares


def discounted_cash_flow(fcf, discount_rate, growth, years=None,
                         terminal_growth=0.02, net_debt=0.0, shares=None):
    """Two-stage DCF: an explicit forecast plus a Gordon-growth terminal value.

    fcf             : the latest actual free cash flow - the year-0 base the
                      forecast grows from.
    discount_rate   : annual discount rate / WACC, as a fraction (0.09 == 9%).
    growth          : either one growth rate applied to every forecast year,
                      or an iterable of per-year rates (its length is the
                      horizon and ``years`` is then ignored).
    years           : forecast horizon in years; required when ``growth`` is a
                      single rate, ignored when it is an iterable.
    terminal_growth : perpetual growth past the forecast, as a fraction
                      (default 0.02). Must be below ``discount_rate``.
    net_debt        : total debt minus cash (default 0); see
                      ``equity_from_enterprise``.
    shares          : shares outstanding. If given the result is per share,
                      otherwise it is the total equity value.

    Returns the intrinsic equity value (or per-share value with ``shares``).
    The sum of discounted explicit cash flows is the enterprise value before
    the terminal value; ``net_debt`` and ``shares`` then take it to equity.

    >>> round(discounted_cash_flow(100, 0.09, 0.05, 5), 2)
    1656.27
    >>> round(discounted_cash_flow(100, 0.09, [0.08, 0.06, 0.04], shares=100), 4)
    16.2701
    """
    rates = _growth_path(growth, years)
    pv_explicit = 0.0
    cash = float(fcf)
    for t, g in enumerate(rates, start=1):
        cash *= 1.0 + g
        pv_explicit += cash / (1.0 + discount_rate) ** t
    n = len(rates)
    terminal = gordon_growth_value(
        cash * (1.0 + terminal_growth), discount_rate, terminal_growth
    )
    pv_terminal = terminal / (1.0 + discount_rate) ** n
    enterprise_value = pv_explicit + pv_terminal
    return equity_from_enterprise(enterprise_value, net_debt, shares)


def multiple_value(metric_per_share, multiple):
    """Per-share value from an equity valuation multiple.

    metric_per_share : the per-share fundamental the multiple applies to -
                       EPS for P/E, sales per share for P/S, book value per
                       share for P/B, FCF per share for P/FCF.
    multiple         : the multiple you judge fair for that metric.

    Returns ``metric_per_share * multiple``. This is an *equity* multiple; for
    an enterprise multiple (EV/EBITDA, EV/Sales) use ``ev_multiple_value``.

    >>> multiple_value(6.5, 28)
    182.0
    """
    return metric_per_share * multiple


def ev_multiple_value(metric, multiple, net_debt=0.0, shares=None):
    """Value from an enterprise-value multiple (EV/EBITDA, EV/Sales, ...).

    metric   : the whole-company metric the multiple applies to (total EBITDA,
               total sales), same currency unit throughout.
    multiple : the EV multiple you judge fair for that metric.
    net_debt : total debt minus cash (default 0).
    shares   : shares outstanding. If given the result is equity value per
               share, otherwise total equity value.

    ``metric * multiple`` is the implied enterprise value;
    ``equity_from_enterprise`` then nets debt and divides by shares.

    >>> round(ev_multiple_value(120_000, 14, net_debt=200_000, shares=15_000), 4)
    98.6667
    """
    return equity_from_enterprise(metric * multiple, net_debt, shares)


def implied_growth_rate(price, fcf, discount_rate, years,
                        terminal_growth=0.02, net_debt=0.0, shares=None,
                        tol=1e-9, max_iter=200):
    """Reverse DCF: the constant forecast-stage growth rate ``price`` implies.

    Solves ``discounted_cash_flow(fcf, discount_rate, g, years, ...) == price``
    for ``g`` by bisection - the DCF value rises monotonically with ``g`` when
    every other input is fixed. Pass ``price`` as a per-share figure when you
    pass ``shares``, and as a total equity value otherwise.

    price           : the market value to match (per share if ``shares`` given).
    fcf, discount_rate, years, terminal_growth, net_debt, shares
                    : passed straight through to ``discounted_cash_flow``.
    tol, max_iter   : bisection tolerance on ``g`` and iteration cap.

    Returns the implied annual growth rate as a fraction. Raises
    ``ValueError`` if the price cannot be bracketed for growth in
    ``(-0.999, 20]``.

    >>> g = implied_growth_rate(1656.27, 100, 0.09, 5)
    >>> round(g, 4)
    0.05
    """
    if years is None or years < 1:
        raise ValueError("years must be a positive integer")

    def value(g):
        return discounted_cash_flow(
            fcf, discount_rate, g, years,
            terminal_growth=terminal_growth, net_debt=net_debt, shares=shares,
        )

    lo, hi = -0.9, 0.5
    while value(hi) < price:
        hi += 0.25
        if hi > 20.0:
            raise ValueError("price implies an implausibly high growth rate")
    while value(lo) > price:
        lo -= 0.25
        if lo <= -0.999:
            raise ValueError("price implies an implausibly low growth rate")

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        if value(mid) < price:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)
