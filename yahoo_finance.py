#!/usr/bin/env python3
"""
Shared helpers for Yahoo Finance's public endpoints. No API key required.

Used by stock_price_history.py, stock_candlestick_chart.py, stock_rebased_chart.py
and stock_risk.py for the --range/--last/--start/--end window flags and for
parsing chart results (their data now comes from price_source.py, which
returns the same shape), by market_top_volume.py for the
cookie + crumb handshake, by stock_intrinsic_value.py and stock_holders.py
for the quoteSummary fetch built on that handshake
(stock_fundamental.py gets it through stock_intrinsic_value.py's fetch),
and by app/stock_information/stock_info_server.py for its quote (the last
user of the chart endpoint itself, fetch_history()). Each caller
keeps its own row shaping (rounding, date formatting, which rows to drop) and
its own output stage; everything up to and including the HTTP call and the
raw-payload navigation lives here.

It is also the Yahoo adapter behind stock_data.py: analyst_view() and
earnings_view() turn quoteSummary data into stock_data's provider-neutral
shape, for stock_analyst_targets.py and stock_earnings_calendar.py. The other
quoteSummary scripts still read the raw modules themselves until they move
behind stock_data.py too.
"""

import datetime as dt

import requests

from cli_utils import positive_int

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# Yahoo rejects requests without a browser-like User-Agent.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
REQUEST_TIMEOUT = 15

VALID_RANGES = [
    "5d", "1mo", "3mo", "6mo", "ytd", "1y", "2y", "5y", "10y", "max",
]
SECONDS_PER_DAY = 86400

# Cookie + crumb handshake for the endpoints that need it (the generic
# screener and quoteSummary). The cookie pages are tried in order until one
# answers; the crumb is tied to the cookies that request set.
COOKIE_URLS = ("https://fc.yahoo.com", "https://finance.yahoo.com")
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"

QUOTE_SUMMARY_HOSTS = [
    "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}",
    "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}",
]


def parse_date(value):
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise ValueError(f"invalid date {value!r}, expected YYYY-MM-DD")


def add_window_args(parser, default_range, last_help):
    """Add the shared time-window flags to an argparse ``parser``.

    ``--range`` and ``--last`` are mutually exclusive; ``--start`` / ``--end``
    sit outside the group and take priority in build_params().
    """
    window = parser.add_mutually_exclusive_group()
    window.add_argument(
        "--range",
        choices=VALID_RANGES,
        default=default_range,
        help=f"Look-back window (default: {default_range})",
    )
    window.add_argument(
        "--last",
        type=positive_int,
        metavar="N",
        help=last_help,
    )
    parser.add_argument("--start", help="Start date YYYY-MM-DD (with optional --end)")
    parser.add_argument("--end", help="End date YYYY-MM-DD (defaults to today)")


def session_datetime(timestamp, gmtoffset):
    """A Yahoo UTC epoch ``timestamp`` as a naive datetime in exchange-local
    time, so its date is the exchange's own trading day."""
    return dt.datetime.fromtimestamp(timestamp + gmtoffset, dt.timezone.utc).replace(tzinfo=None)


def fetch_crumb(session):
    """Pick up Yahoo's consent cookie on ``session`` and return its crumb.

    Returns ``None`` when no usable crumb comes back (an error page, an HTML
    consent wall, or an empty body); callers decide whether that is fatal.
    """
    for url in COOKIE_URLS:
        try:
            session.get(url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            continue
        else:
            break
    try:
        resp = session.get(CRUMB_URL, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None
    text = resp.text.strip()
    if resp.ok and text and "<" not in text and len(text) < 64:
        return text
    return None


def crumb_session():
    """A ``requests.Session`` with the browser-like HEADERS, plus its crumb (or None)."""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session, fetch_crumb(session)


def fetch_quote_summary(symbol, modules):
    """Return the ``quoteSummary`` result for ``symbol``: a dict keyed by the
    requested ``modules`` (Yahoo omits any it has no data for).

    Tries each host with the crumb, then each without it, and raises
    ``requests.RequestException`` carrying the last error if none answers.
    """
    session, crumb = crumb_session()
    params = {"modules": ",".join(modules), "formatted": "false"}
    attempts = [(host, True) for host in QUOTE_SUMMARY_HOSTS]
    attempts += [(host, False) for host in QUOTE_SUMMARY_HOSTS]

    last_error = "no response"
    for host, use_crumb in attempts:
        if use_crumb and not crumb:
            continue
        query = dict(params)
        if use_crumb:
            query["crumb"] = crumb
        try:
            resp = session.get(
                host.format(symbol=symbol), params=query, timeout=REQUEST_TIMEOUT
            )
            payload = resp.json()
        except ValueError:
            last_error = f"non-JSON response (HTTP {resp.status_code})"
            continue
        except requests.RequestException as exc:
            last_error = str(exc)
            continue
        envelope = payload.get("quoteSummary") or {}
        error = envelope.get("error")
        if error:
            last_error = error.get("description") or error.get("code") or str(error)
            continue
        results = envelope.get("result")
        if results:
            return results[0]
        last_error = "no fundamentals in response"
    raise requests.RequestException(last_error)


def summary_num(node, *path):
    """Dig ``path`` out of a nested quoteSummary dict; unwrap Yahoo's
    {"raw": ...}; -> float|None."""
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if isinstance(node, dict):
        node = node.get("raw")
    if isinstance(node, bool):
        return None
    return float(node) if isinstance(node, (int, float)) else None


def summary_text(node, *path):
    """Dig ``path`` out of a nested quoteSummary dict -> non-empty str|None."""
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, str) and node else None


def build_params(interval="1d", range_=None, start=None, end=None, last=None):
    """Return the query params for the chart call.

    The window is chosen by, in priority order: an explicit start/end pair,
    then --last N, then a --range keyword. The --last look-back window is
    widened for coarser intervals so N whole bars are actually covered.
    """
    params = {"interval": interval, "includeAdjustedClose": "true"}

    if start or end:
        start_dt = parse_date(start) if start else None
        end_dt = parse_date(end) if end else dt.datetime.now(dt.timezone.utc)
        if start_dt is None:
            raise ValueError("--end requires --start")
        if end_dt < start_dt:
            raise ValueError("--end must not be before --start")
        params["period1"] = int(start_dt.timestamp())
        # pad the end by a day so the final session is inclusive
        params["period2"] = int(end_dt.timestamp()) + SECONDS_PER_DAY
    elif last:
        # Fetch a generous calendar window, then let the caller trim to the
        # last N rows. ~1.6 calendar days per trading day, plus slack for
        # holidays; more for weekly/monthly bars.
        lookback_days = last * 2 + 10
        if interval == "1wk":
            lookback_days = last * 9 + 14
        elif interval == "1mo":
            lookback_days = last * 32 + 31
        start_dt = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)
        params["period1"] = int(start_dt.timestamp())
        params["period2"] = int(dt.datetime.now(dt.timezone.utc).timestamp()) + SECONDS_PER_DAY
    else:
        params["range"] = range_

    return params


def fetch_history(symbol, params):
    response = requests.get(
        CHART_URL.format(symbol=symbol),
        params=params,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    # Yahoo returns a JSON error body with a 404/400 for bad symbols.
    try:
        payload = response.json()
    except ValueError:
        response.raise_for_status()
        raise
    error = payload.get("chart", {}).get("error")
    if error:
        raise requests.RequestException(
            error.get("description") or error.get("code") or str(error)
        )
    results = payload.get("chart", {}).get("result")
    if not results:
        raise requests.RequestException("no data returned for symbol")
    return results[0]


def meta_summary(meta, fallback_symbol=None):
    """Pull the display fields out of a chart result's ``meta`` block.

    Returns a ``(symbol, exchange, currency)`` tuple: ``symbol`` falls back
    to ``fallback_symbol`` then ``"?"``, ``exchange`` to ``"?"``, and
    ``currency`` to ``""`` when the payload does not carry them.
    """
    symbol = meta.get("symbol") or fallback_symbol or "?"
    exchange = meta.get("fullExchangeName") or meta.get("exchangeName") or "?"
    currency = meta.get("currency") or ""
    return symbol, exchange, currency


def extract_series(result):
    """Return (meta, series) from a Yahoo chart result.

    series is a dict of parallel lists straight off the payload - "timestamp",
    "open", "high", "low", "close", "volume" - plus "adjclose" (a list or
    None) and the resolved "gmtoffset". Callers turn these into rows.
    """
    meta = result.get("meta", {})
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    adj_block = result.get("indicators", {}).get("adjclose") or [{}]
    adj_closes = adj_block[0].get("adjclose") if adj_block else None
    return meta, {
        "gmtoffset": meta.get("gmtoffset", 0) or 0,
        "timestamp": result.get("timestamp") or [],
        "open": quote.get("open") or [],
        "high": quote.get("high") or [],
        "low": quote.get("low") or [],
        "close": quote.get("close") or [],
        "volume": quote.get("volume") or [],
        "adjclose": adj_closes,
    }


# --------------------------------------------------------------------------- #
# stock_data.py adapter: quoteSummary to provider-neutral shapes               #
# --------------------------------------------------------------------------- #
SOURCE = "Yahoo Finance"

ANALYST_MODULES = ["price", "financialData", "recommendationTrend", "upgradeDowngradeHistory"]
RATING_FIELDS = [("strong_buy", "strongBuy"), ("buy", "buy"), ("hold", "hold"),
                 ("sell", "sell"), ("strong_sell", "strongSell")]
TREND_PERIODS = ("0m", "-1m", "-2m", "-3m")
GRADE_ACTIONS = {"up": "upgrade", "down": "downgrade", "init": "initiate",
                 "reit": "reiterate", "main": "maintain"}
TARGET_ACTIONS = {"Raises": "raised", "Lowers": "lowered", "Maintains": "maintained",
                  "Announces": "announced", "Adjusts": "adjusted"}


def _profile(modules):
    """name, exchange, currency from the ``price`` module."""
    return {
        "name": summary_text(modules, "price", "longName")
        or summary_text(modules, "price", "shortName"),
        "exchange": summary_text(modules, "price", "exchangeName"),
        "currency": summary_text(modules, "price", "currency") or "",
    }


def _recommendation_trend(modules):
    """Rating counts per month from ``recommendationTrend``, newest first;
    a month with no counts at all is dropped."""
    rows = []
    for entry in (modules.get("recommendationTrend") or {}).get("trend") or []:
        counts = {key: summary_num(entry, raw) for key, raw in RATING_FIELDS}
        if all(v is None for v in counts.values()):
            continue
        rows.append({"period": entry.get("period"),
                     **{key: int(v or 0) for key, v in counts.items()}})
    order = {p: i for i, p in enumerate(TREND_PERIODS)}
    rows.sort(key=lambda r: order.get(r["period"], len(order)))
    return rows


def _positive(value):
    """A price target, or None for Yahoo's 0 placeholder (no target given)."""
    return value if isinstance(value, (int, float)) and value > 0 else None


def _analyst_actions(modules, days, now=None):
    """Firm-level actions from ``upgradeDowngradeHistory`` in the last ``days``,
    newest first. ``now`` (epoch seconds) is for tests."""
    now = now if now is not None else dt.datetime.now(dt.timezone.utc).timestamp()
    cutoff = now - days * SECONDS_PER_DAY
    dated = []
    for entry in (modules.get("upgradeDowngradeHistory") or {}).get("history") or []:
        epoch = entry.get("epochGradeDate")
        if not isinstance(epoch, (int, float)) or epoch < cutoff:
            continue
        action = entry.get("action")
        target_action = entry.get("priceTargetAction")
        dated.append((epoch, {
            "date": dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%d"),
            "firm": entry.get("firm") or None,
            "action": GRADE_ACTIONS.get(action, action or None),
            "from_grade": entry.get("fromGrade") or None,
            "to_grade": entry.get("toGrade") or None,
            "target_action": TARGET_ACTIONS.get(target_action, (target_action or "").lower() or None),
            "target": _positive(entry.get("currentPriceTarget")),
            "prior_target": _positive(entry.get("priorPriceTarget")),
        }))
    dated.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in dated]


def parse_analyst_view(modules, days, now=None):
    """stock_data.analyst_view()'s shape from quoteSummary ``modules``."""
    def fd(key):
        return summary_num(modules, "financialData", key)

    analysts = fd("numberOfAnalystOpinions")
    key = summary_text(modules, "financialData", "recommendationKey")
    return {
        "source": SOURCE,
        "notes": [],
        **_profile(modules),
        "price": fd("currentPrice") or summary_num(modules, "price", "regularMarketPrice"),
        "analysts": None if analysts is None else int(analysts),
        "targets": {key: fd(f"target{label}Price") for key, label in
                    (("low", "Low"), ("median", "Median"), ("mean", "Mean"), ("high", "High"))},
        "recommendation": {"key": None if key in (None, "none") else key,
                           "mean": fd("recommendationMean")},
        "trend": _recommendation_trend(modules),
        "actions": _analyst_actions(modules, days, now),
    }


def analyst_view(symbol, days):
    """Fetch ``symbol``'s analyst data and return stock_data's neutral shape."""
    return parse_analyst_view(fetch_quote_summary(symbol, ANALYST_MODULES), days)


EARNINGS_MODULES = ["price", "financialData", "defaultKeyStatistics", "calendarEvents",
                    "earningsHistory", "earnings"]
# Quote currencies in a minor unit (pence, agorot, cents). Yahoo gives their
# dividend in the major or declared currency without saying which.
MINOR_UNIT_CURRENCIES = {"GBp", "GBX", "ILA", "ZAc"}


def _utc(timestamp):
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)


def _iso_date(timestamp):
    return None if timestamp is None else _utc(timestamp).strftime("%Y-%m-%d")


def _estimate(earnings, prefix):
    values = {
        "low": summary_num(earnings, f"{prefix}Low"),
        "average": summary_num(earnings, f"{prefix}Average"),
        "high": summary_num(earnings, f"{prefix}High"),
    }
    return values if any(v is not None for v in values.values()) else None


def _next_earnings(modules):
    """The next (or latest-known) earnings event from ``calendarEvents``, or None.

    When Yahoo has no confirmed date it gives a window of two timestamps;
    ``date`` is the start and ``date_end`` the end of that window.
    """
    earnings = (modules.get("calendarEvents") or {}).get("earnings") or {}
    stamps = sorted(
        summary_num({"t": t}, "t") for t in earnings.get("earningsDate") or []
    )
    stamps = [int(t) for t in stamps if t is not None]
    if not stamps:
        return None
    return {
        "date": _iso_date(stamps[0]),
        "date_end": _iso_date(stamps[-1]),
        "datetime_utc": _utc(stamps[0]).strftime("%Y-%m-%dT%H:%MZ"),
        "is_estimate": bool(earnings.get("isEarningsDateEstimate")) or len(stamps) > 1,
        "eps_estimate": _estimate(earnings, "earnings"),
        "revenue_estimate": _estimate(earnings, "revenue"),
    }


def _dividend(modules, currency):
    """Ex-dividend / payment dates and the last dividend paid, or None if Yahoo has none."""
    calendar = modules.get("calendarEvents") or {}
    ex_date = _iso_date(summary_num(calendar, "exDividendDate"))
    pay_date = _iso_date(summary_num(calendar, "dividendDate"))
    last_amount = summary_num(modules, "defaultKeyStatistics", "lastDividendValue")
    if ex_date is None and pay_date is None and last_amount is None:
        return None
    return {
        "ex_dividend_date": ex_date,
        "payment_date": pay_date,
        "last_amount": last_amount,
        "last_amount_date": _iso_date(
            summary_num(modules, "defaultKeyStatistics", "lastDividendDate")
        ),
        "amount_currency": None if currency in MINOR_UNIT_CURRENCIES else currency or None,
    }


def _earnings_history(modules):
    """The last quarters' EPS from ``earningsHistory``, oldest first.

    The report date and fiscal-quarter label come from the ``earnings``
    module's chart, matched on the quarter-end date.
    """
    chart = ((modules.get("earnings") or {}).get("earningsChart") or {}).get("quarterly") or []
    by_end = {}
    for entry in chart:
        end = summary_num(entry, "periodEndDate")
        if end is not None:
            by_end[_iso_date(end)] = entry

    rows = []
    for entry in (modules.get("earningsHistory") or {}).get("history") or []:
        quarter_end = _iso_date(summary_num(entry, "quarter"))
        actual = summary_num(entry, "epsActual")
        estimate = summary_num(entry, "epsEstimate")
        if quarter_end is None or (actual is None and estimate is None):
            continue
        match = by_end.get(quarter_end, {})
        rows.append({
            "quarter_end": quarter_end,
            "fiscal_quarter": summary_text(match, "fiscalQuarter"),
            "reported_date": _iso_date(summary_num(match, "reportedDate")),
            "eps_estimate": estimate,
            "eps_actual": actual,
            "surprise_pct": summary_num(entry, "surprisePercent"),
            "currency": summary_text(entry, "currency"),
        })
    rows.sort(key=lambda r: r["quarter_end"])
    return rows


def parse_earnings_view(modules):
    """stock_data.earnings_view()'s shape from quoteSummary ``modules``."""
    profile = _profile(modules)
    history = _earnings_history(modules)
    return {
        "source": SOURCE,
        "notes": [],
        **profile,
        # EPS and revenue estimates are in the reporting currency, which can
        # differ from the trading currency (VOD.L trades in GBp, reports in EUR).
        "reporting_currency": summary_text(modules, "financialData", "financialCurrency")
        or next((r["currency"] for r in reversed(history) if r["currency"]), None),
        "next_earnings": _next_earnings(modules),
        "dividend": _dividend(modules, profile["currency"]),
        "earnings_history": history,
    }


def earnings_view(symbol):
    """Fetch ``symbol``'s earnings calendar and return stock_data's neutral shape."""
    return parse_earnings_view(fetch_quote_summary(symbol, EARNINGS_MODULES))
