#!/usr/bin/env python3
"""
Small, dependency-free technical indicators over a price series.

Every function takes ``prices`` as an iterable of numbers, oldest session
first (e.g. the ``close`` field of each row from stock_close_history.py's
``--json`` output). Series transforms (``moving_average``,
``price_vs_moving_average``) return a list the same length as the input so the
result lines up session-for-session with the source rows; classifiers
(``trend``) return a single verdict.

Not a CLI - this module is imported, not run.
"""


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
    mean price. If that fitted move is smaller than ``flat_threshold`` in
    magnitude the series is called ``"flat"`` (direction is just noise);
    otherwise its sign decides up vs down.

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

    # Fitted fractional move from the first fitted point to the last.
    fitted_move = _ols_slope(prices) * (len(prices) - 1) / mean
    if abs(fitted_move) < flat_threshold:
        return "flat"
    return "up" if fitted_move > 0 else "down"
