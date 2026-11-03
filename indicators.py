#!/usr/bin/env python3
"""
Small, dependency-free technical indicators over a price series.

Every function takes ``prices`` as an iterable of numbers, oldest session
first (e.g. the ``close`` field of each row from stock_price_history.py's
``--json`` output). Series transforms (``moving_average``,
``price_vs_moving_average``, ``moving_average_cross``,
``moving_average_cross_flip``, ``rebase``, ``returns``) return a list the same
length as the input so the result lines up session-for-session with the source
rows; classifiers (``trend``) return a single verdict, and the risk metrics
(``volatility``, ``max_drawdown``, ``correlation``) a single summary of the
whole series.

Not a CLI - this module is imported, not run.
"""

import math


def moving_average(prices, n):
    """Simple moving average of a price series over a window of ``n`` sessions.

    prices : iterable of numbers, oldest session first.
    n      : window size in sessions (a positive int).

    Returns a list the same length as ``prices``: element ``i`` is the mean of
    ``prices[i - n + 1 .. i]``, or ``None`` for the first ``n - 1`` positions
    where a full window isn't available yet.

    >>> moving_average([1, 2, 3, 4, 5], 3)
    [None, None, 2.0, 3.0, 4.0]
    """
    if n < 1:
        raise ValueError("n must be a positive integer")
    prices = list(prices)
    return [
        sum(prices[i - n + 1:i + 1]) / n if i >= n - 1 else None
        for i in range(len(prices))
    ]


def price_vs_moving_average(prices, n):
    """Where each session's price sits relative to its ``n``-session SMA.

    prices : iterable of numbers, oldest session first.
    n      : moving-average window in sessions (a positive int).

    Returns a list the same length as ``prices``: ``"above"``, ``"below"`` or
    ``"equal"`` for each session where the SMA is defined, and ``None`` for the
    first ``n - 1`` positions where it isn't yet. Take ``[-1]`` for the current
    reading.

    >>> price_vs_moving_average([10, 10, 10, 7, 13], 3)
    [None, None, 'equal', 'below', 'above']
    """
    prices = list(prices)
    averages = moving_average(prices, n)
    out = []
    for price, avg in zip(prices, averages):
        if avg is None:
            out.append(None)
        elif price > avg:
            out.append("above")
        elif price < avg:
            out.append("below")
        else:
            out.append("equal")
    return out


def moving_average_cross(prices, fast, slow):
    """Where the ``fast`` SMA sits relative to the ``slow`` SMA, per session.

    prices     : iterable of numbers, oldest session first.
    fast, slow  : the two moving-average windows in sessions (positive ints).
                  ``fast`` is meant to be the shorter one, but the function
                  just compares whichever two windows it is given.

    Returns a list the same length as ``prices``: ``"above"``, ``"below"`` or
    ``"equal"`` for each session where **both** averages are defined (from
    index ``max(fast, slow) - 1`` on), and ``None`` before that. Take ``[-1]``
    for the current reading; a change in the value marks a crossover (the
    "golden cross" / "death cross" when ``fast``/``slow`` are e.g. 50/200).

    >>> moving_average_cross([1, 2, 3, 4, 5, 6], 2, 4)
    [None, None, None, 'above', 'above', 'above']
    """
    prices = list(prices)
    fast_ma = moving_average(prices, fast)
    slow_ma = moving_average(prices, slow)
    out = []
    for f, s in zip(fast_ma, slow_ma):
        if f is None or s is None:
            out.append(None)
        elif f > s:
            out.append("above")
        elif f < s:
            out.append("below")
        else:
            out.append("equal")
    return out


def moving_average_cross_flip(prices, fast, slow):
    """Flag each session where the ``fast``/``slow`` MA cross flips sides.

    prices     : iterable of numbers, oldest session first.
    fast, slow  : the two moving-average windows in sessions (positive ints),
                  passed straight through to ``moving_average_cross``.

    Runs ``moving_average_cross`` and returns a list the same length as
    ``prices``: ``True`` on a session where the cross has just gone from
    ``"below"`` to ``"above"`` or from ``"above"`` to ``"below"`` since the
    last session it was decisively one side or the other, and ``False``
    otherwise. Runs of ``"equal"`` between the two sides are stepped over, so
    the flip still reports on the session where the new side first shows.
    ``"equal"`` sessions, sessions where the cross hasn't switched sides, and
    the first decisive session (nothing before it to differ from) are all
    ``False``; sessions where the cross isn't defined yet are ``None``, as in
    ``moving_average_cross``. Take ``[-1]`` for the current reading.

    >>> moving_average_cross_flip([3, 1, 1, 2, 3], 1, 2)
    [None, False, False, True, False]
    >>> moving_average_cross_flip([1, 2, 3, 4, 5, 6], 2, 4)
    [None, None, None, False, False, False]
    """
    cross = moving_average_cross(prices, fast, slow)
    out = []
    prev_side = None
    for value in cross:
        if value is None:
            out.append(None)
            continue
        if value == "equal":
            out.append(False)
            continue
        out.append(prev_side is not None and value != prev_side)
        prev_side = value
    return out


def rebase(prices, n=0):
    """Rescale a price series so its ``n``-th session reads as 100.

    prices : iterable of numbers, oldest session first.
    n      : index of the reference session (default 0, the first price).

    Returns a list the same length as ``prices``: each element is the ratio
    of that session's price to ``prices[n]``, scaled so ``prices[n]`` itself
    maps to 100.

    >>> rebase([50, 100, 150])
    [100.0, 200.0, 300.0]
    >>> rebase([50, 100, 150], n=1)
    [50.0, 100.0, 150.0]
    """
    prices = list(prices)
    base = prices[n]
    if base == 0:
        raise ValueError("reference price (prices[n]) must be non-zero")
    return [price / base * 100 for price in prices]


def _ols_slope(values):
    """Least-squares slope of ``values`` against x = 0, 1, 2, ... (per step)."""
    m = len(values)
    x_mean = (m - 1) / 2
    y_mean = sum(values) / m
    sxx = sum((i - x_mean) ** 2 for i in range(m))
    sxy = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    return sxy / sxx  # sxx > 0 whenever m >= 2


def trend(prices, window=None, flat_threshold=0.01):
    """Classify a price series as ``"up"``, ``"down"`` or ``"flat"``.

    Fits a least-squares line through the closes and measures the move implied
    by that line from its first fitted point to its last, as a fraction of the
    magnitude of the mean price (so the sign always tracks the slope, even for
    an all-negative series). If that fitted move is smaller than
    ``flat_threshold`` in magnitude the series is called ``"flat"`` (direction
    is just noise); otherwise its sign decides up vs down.

    prices         : iterable of numbers, oldest session first (>= 2 values).
    window         : if given, only the last ``window`` prices are considered.
    flat_threshold : dead zone as a fraction of mean price, applied to the
                     fitted move across the whole span (default 0.01 = 1%).
                     Raise it to ignore weaker trends, lower it to be more
                     sensitive.

    >>> trend([1, 2, 3, 4, 5])
    'up'
    >>> trend([5, 4, 3, 2, 1])
    'down'
    >>> trend([10, 10, 10, 10])
    'flat'
    """
    prices = list(prices)
    if window is not None:
        if window < 2:
            raise ValueError("window must be at least 2")
        prices = prices[-window:]
    if len(prices) < 2:
        raise ValueError("need at least 2 prices to determine a trend")

    mean = sum(prices) / len(prices)
    if mean == 0:
        return "flat"

    # Fitted fractional move from the first fitted point to the last. Scale
    # by abs(mean), not mean, so a negative-valued series doesn't flip sign.
    fitted_move = _ols_slope(prices) * (len(prices) - 1) / abs(mean)
    if abs(fitted_move) < flat_threshold:
        return "flat"
    return "up" if fitted_move > 0 else "down"


def returns(prices):
    """Session-to-session fractional change of a price series.

    prices : iterable of numbers, oldest session first.

    Returns a list the same length as ``prices``: element ``i`` is
    ``prices[i] / prices[i - 1] - 1`` (``0.05`` = up 5% on the session before),
    and ``None`` at position 0, which has no earlier session to compare with.
    Raises ``ValueError`` if any price but the last is ``0``.

    >>> returns([100, 150, 75])
    [None, 0.5, -0.5]
    """
    prices = list(prices)
    if not prices:
        return []
    if any(price == 0 for price in prices[:-1]):
        raise ValueError("prices must be non-zero to compute returns")
    return [None] + [
        prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))
    ]


def volatility(prices, periods_per_year=252):
    """Annualized volatility: how widely the series swung session to session.

    The sample standard deviation of ``returns(prices)``, scaled by
    ``sqrt(periods_per_year)`` so series of different lengths read on the same
    yearly scale. It counts up-moves and down-moves alike.

    prices           : iterable of numbers, oldest session first (>= 3 values,
                       i.e. at least 2 returns). Slice it first (e.g.
                       ``prices[-21:]``) to measure a recent stretch only.
    periods_per_year : sessions in a year at the series' interval (default 252
                       trading days; 52 for weekly, 12 for monthly, 365 for a
                       coin that trades every day). Pass 1 for the plain
                       per-session figure.

    Returns a fraction (``0.24`` = 24% a year). Raises ``ValueError`` on fewer
    than 3 prices, a non-positive ``periods_per_year``, or (via ``returns``) a
    zero price.

    >>> round(volatility([100, 150, 75], periods_per_year=1), 4)
    0.7071
    >>> volatility([10, 10, 10])
    0.0
    """
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    rets = returns(prices)[1:]
    if len(rets) < 2:
        raise ValueError("need at least 3 prices to compute volatility")
    mean = sum(rets) / len(rets)
    variance = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(variance) * math.sqrt(periods_per_year)


def max_drawdown(prices):
    """The worst peak-to-trough fall in a price series.

    Walks the series keeping the highest price seen so far; each session's
    drawdown is its fall from that running peak. The largest fall wins (the
    earliest one, on a tie).

    prices : iterable of positive numbers, oldest session first (>= 1 value).

    Returns a dict:

    - ``drawdown`` : the fall as a fraction, ``<= 0`` (``-0.25`` = down 25%
      from the peak); ``0.0`` if the series never fell below an earlier high.
    - ``peak``     : index of the high the fall started from.
    - ``trough``   : index of the low it reached.
    - ``recovery`` : index of the first session after the trough that closed
      back at or above the peak's price, or ``None`` if it hasn't yet.

    ``peak``, ``trough`` and ``recovery`` are all ``None`` when ``drawdown`` is
    ``0.0``. Map the indices back to dates with the caller's own rows. Raises
    ``ValueError`` on an empty series or a non-positive price.

    >>> max_drawdown([100, 120, 90, 110])
    {'drawdown': -0.25, 'peak': 1, 'trough': 2, 'recovery': None}
    >>> max_drawdown([100, 50, 100])
    {'drawdown': -0.5, 'peak': 0, 'trough': 1, 'recovery': 2}
    """
    prices = list(prices)
    if not prices:
        raise ValueError("need at least 1 price to compute a drawdown")
    if any(price <= 0 for price in prices):
        raise ValueError("prices must be positive to compute a drawdown")

    running_peak = 0
    worst, peak, trough = 0.0, None, None
    for i, price in enumerate(prices):
        if price > prices[running_peak]:
            running_peak = i
        fall = price / prices[running_peak] - 1
        if fall < worst:
            worst, peak, trough = fall, running_peak, i

    recovery = None
    if trough is not None:
        recovery = next(
            (i for i in range(trough + 1, len(prices))
             if prices[i] >= prices[peak]),
            None,
        )
    return {"drawdown": worst, "peak": peak, "trough": trough,
            "recovery": recovery}


def correlation(prices_a, prices_b):
    """How closely two price series moved together, from -1 to +1.

    The Pearson correlation of the two series' ``returns`` - their
    session-to-session changes, not the raw prices, since two prices that both
    drifted up would otherwise look related even if their daily moves weren't.
    Near ``+1`` they rose and fell on the same sessions, near ``0`` there was
    no consistent link, near ``-1`` one tended to rise as the other fell.

    prices_a, prices_b : iterables of numbers, oldest session first, the same
                         length and aligned session for session (element
                         ``i`` of each is the same date). Lining up two
                         tickers whose exchanges keep different holidays is
                         the caller's job; this only sees two lists.

    Returns a float, or ``None`` if either series never moved (its returns
    are all the same, so a correlation isn't defined). Raises ``ValueError``
    if the lengths differ, there are fewer than 3 prices, or (via
    ``returns``) a price is zero.

    >>> correlation([100, 150, 75], [10, 15, 7.5])
    1.0
    >>> correlation([100, 150, 75], [100, 50, 75])
    -1.0
    """
    a = returns(prices_a)[1:]
    b = returns(prices_b)[1:]
    if len(a) != len(b):
        raise ValueError("price series must be the same length")
    if len(a) < 2:
        raise ValueError("need at least 3 prices to compute a correlation")
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    if var_a == 0 or var_b == 0:
        return None
    return cov / math.sqrt(var_a * var_b)
