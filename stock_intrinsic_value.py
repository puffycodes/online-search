#!/usr/bin/env python3
"""
Estimate a stock's intrinsic value every way valuation.py can, from data
pulled off Yahoo Finance's public ``quoteSummary`` endpoint. No API key or
authentication required (a cookie + crumb are fetched automatically).

Give it a ticker in Yahoo's notation (AAPL, VOD.L, D05.SI, SAP.DE, ...). The
script retrieves the fundamentals each method needs - trailing free cash
flow, EBITDA, revenue, share count, debt and cash, EPS, book value, beta,
dividend, current multiples, and the analyst long-term growth estimate - then
runs every function in valuation.py that it has inputs for:

- two-stage discounted cash flow            (discounted_cash_flow)
- reverse DCF: the growth the price implies  (implied_growth_rate)
- constant-growth dividend discount model    (gordon_growth_value)
- P/E, P/S and Graham earnings multiples     (multiple_value)
- EV/EBITDA multiple                         (ev_multiple_value)
- reported enterprise value -> equity/share  (equity_from_enterprise)

The discount rate defaults to CAPM from the stock's beta, and the forecast
growth to the analyst 5-year estimate; override either (and the multiples,
horizon, and CAPM parameters) with the flags below. Supports --json for
structured output. On failure the process exits non-zero and prints
{"error": "..."} to stderr.
"""

import argparse
import json

import requests

import yahoo_finance as yf
from cli_utils import die, positive_int
from valuation import (
    discounted_cash_flow,
    equity_from_enterprise,
    ev_multiple_value,
    gordon_growth_value,
    implied_growth_rate,
    multiple_value,
)

QUOTE_SUMMARY_HOSTS = [
    "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}",
    "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}",
]
COOKIE_URL = "https://fc.yahoo.com"
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
MODULES = [
    "price",
    "summaryDetail",
    "defaultKeyStatistics",
    "financialData",
    "earningsTrend",
    "summaryProfile",
]

# Assumption defaults, all fractions (0.09 == 9%). Every one is overridable.
DEFAULT_DISCOUNT_RATE = 0.09   # used only when there is no beta to run CAPM
DEFAULT_GROWTH = 0.05          # used only when there is no analyst estimate
DEFAULT_TERMINAL_GROWTH = 0.025
DEFAULT_YEARS = 10
DEFAULT_RISK_FREE = 0.04
DEFAULT_ERP = 0.05            # equity risk premium
GRAHAM_PE_CAP = 40.0         # keep 8.5 + 2g sane for high growth assumptions


# --------------------------------------------------------------------------- #
# Fetch                                                                        #
# --------------------------------------------------------------------------- #
def _crumb_session():
    """A requests.Session carrying Yahoo's consent cookie, plus its crumb."""
    session = requests.Session()
    session.headers.update(yf.HEADERS)
    for url in (COOKIE_URL, "https://finance.yahoo.com"):
        try:
            session.get(url, timeout=yf.REQUEST_TIMEOUT)
        except requests.RequestException:
            continue
        else:
            break
    crumb = None
    try:
        resp = session.get(CRUMB_URL, timeout=yf.REQUEST_TIMEOUT)
        text = resp.text.strip()
        if resp.ok and text and "<" not in text and len(text) < 64:
            crumb = text
    except requests.RequestException:
        pass
    return session, crumb


def fetch_fundamentals(symbol):
    """Return the ``quoteSummary`` module dict for ``symbol`` (raises on failure)."""
    session, crumb = _crumb_session()
    params = {"modules": ",".join(MODULES), "formatted": "false"}
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
                host.format(symbol=symbol), params=query, timeout=yf.REQUEST_TIMEOUT
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


# --------------------------------------------------------------------------- #
# Parse                                                                        #
# --------------------------------------------------------------------------- #
def _num(node, *path):
    """Dig ``path`` out of a nested dict; unwrap Yahoo's {"raw": ...}; -> float|None."""
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if isinstance(node, dict):
        node = node.get("raw")
    if isinstance(node, bool):
        return None
    return float(node) if isinstance(node, (int, float)) else None


def _text(node, *path):
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, str) and node else None


def _analyst_growth(modules, period):
    for entry in (modules.get("earningsTrend") or {}).get("trend") or []:
        if entry.get("period") == period:
            return _num(entry, "growth")
    return None


def collect_inputs(modules):
    """Flatten the raw modules into the numbers the valuation functions need."""
    price = _num(modules, "financialData", "currentPrice")
    price = price if price else _num(modules, "price", "regularMarketPrice")
    market_cap = _num(modules, "price", "marketCap")
    shares = _num(modules, "defaultKeyStatistics", "sharesOutstanding")
    if not shares and market_cap and price:
        shares = market_cap / price

    total_debt = _num(modules, "financialData", "totalDebt")
    total_cash = _num(modules, "financialData", "totalCash")
    net_debt = (
        total_debt - total_cash
        if total_debt is not None and total_cash is not None
        else None
    )
    revenue = _num(modules, "financialData", "totalRevenue")

    return {
        "name": _text(modules, "price", "longName")
        or _text(modules, "price", "shortName"),
        "exchange": _text(modules, "price", "exchangeName"),
        "currency": _text(modules, "price", "currency") or "",
        "sector": _text(modules, "summaryProfile", "sector"),
        "price": price,
        "market_cap": market_cap,
        "shares": shares,
        "free_cash_flow": _num(modules, "financialData", "freeCashflow"),
        "ebitda": _num(modules, "financialData", "ebitda"),
        "total_debt": total_debt,
        "total_cash": total_cash,
        "net_debt": net_debt,
        "revenue": revenue,
        "revenue_per_share": revenue / shares if revenue and shares else None,
        "eps_ttm": _num(modules, "defaultKeyStatistics", "trailingEps"),
        "eps_forward": _num(modules, "defaultKeyStatistics", "forwardEps"),
        "book_value_per_share": _num(modules, "defaultKeyStatistics", "bookValue"),
        "beta": _num(modules, "defaultKeyStatistics", "beta")
        or _num(modules, "summaryDetail", "beta"),
        "trailing_pe": _num(modules, "summaryDetail", "trailingPE"),
        "forward_pe": _num(modules, "summaryDetail", "forwardPE"),
        "price_to_sales": _num(modules, "summaryDetail", "priceToSalesTrailing12Months"),
        "enterprise_value": _num(modules, "defaultKeyStatistics", "enterpriseValue"),
        "ev_to_ebitda": _num(modules, "defaultKeyStatistics", "enterpriseToEbitda"),
        "dividend_rate": _num(modules, "summaryDetail", "dividendRate"),
        "analyst_growth_5y": _analyst_growth(modules, "+5y"),
        "analyst_growth_1y": _analyst_growth(modules, "+1y"),
    }


# --------------------------------------------------------------------------- #
# Assumptions + estimates                                                      #
# --------------------------------------------------------------------------- #
def resolve_assumptions(inputs, args):
    notes = {}

    if args.discount_rate is not None:
        rate = args.discount_rate
        notes["discount_rate"] = "user-supplied"
    elif inputs["beta"] is not None:
        rate = args.risk_free + inputs["beta"] * args.equity_risk_premium
        notes["discount_rate"] = (
            f"CAPM: {args.risk_free:.2%} + {inputs['beta']:.2f} x "
            f"{args.equity_risk_premium:.2%}"
        )
    else:
        rate = DEFAULT_DISCOUNT_RATE
        notes["discount_rate"] = f"default {DEFAULT_DISCOUNT_RATE:.2%} (no beta)"

    if args.growth is not None:
        growth = args.growth
        notes["growth"] = "user-supplied"
    elif inputs["analyst_growth_5y"] is not None:
        growth = inputs["analyst_growth_5y"]
        notes["growth"] = "analyst 5-year EPS growth estimate"
    elif inputs["analyst_growth_1y"] is not None:
        growth = inputs["analyst_growth_1y"]
        notes["growth"] = "analyst 1-year EPS growth estimate"
    else:
        growth = DEFAULT_GROWTH
        notes["growth"] = f"default {DEFAULT_GROWTH:.2%} (no analyst estimate)"

    terminal_growth = args.terminal_growth
    if terminal_growth >= rate:
        rate = terminal_growth + 0.02
        notes["discount_rate"] += f"; raised to {rate:.2%} (must exceed terminal growth)"

    return {
        "discount_rate": rate,
        "growth": growth,
        "terminal_growth": terminal_growth,
        "years": args.years,
        "risk_free": args.risk_free,
        "equity_risk_premium": args.equity_risk_premium,
        "notes": notes,
    }


def _vs_price(price, value):
    """Fractional gap of price over an estimate; positive = price above it."""
    if not price or not value or value <= 0:
        return None
    return price / value - 1.0


def compute_estimates(inputs, assumptions, args):
    price = inputs["price"]
    fcf = inputs["free_cash_flow"]
    shares = inputs["shares"]
    net_debt = inputs["net_debt"] or 0.0
    eps = inputs["eps_ttm"]
    rate = assumptions["discount_rate"]
    growth = assumptions["growth"]
    tg = assumptions["terminal_growth"]
    years = assumptions["years"]

    have_dcf_inputs = bool(fcf and fcf > 0 and shares and shares > 0)
    est = {}
    used = {}

    # 1. Two-stage DCF -------------------------------------------------------- #
    if have_dcf_inputs:
        est["dcf_two_stage"] = discounted_cash_flow(
            fcf, rate, growth, years,
            terminal_growth=tg, net_debt=net_debt, shares=shares,
        )
    else:
        est["dcf_two_stage"] = None

    # 2. Reverse DCF -> implied growth ------------------------------------- #
    if have_dcf_inputs and price:
        try:
            est["reverse_dcf_implied_growth"] = implied_growth_rate(
                price, fcf, rate, years,
                terminal_growth=tg, net_debt=net_debt, shares=shares,
            )
        except ValueError:
            est["reverse_dcf_implied_growth"] = None
    else:
        est["reverse_dcf_implied_growth"] = None

    # 3. Constant-growth dividend discount model -------------------------- #
    # A perpetual model, so it grows the dividend at the sustainable terminal
    # rate - not the (often near-term) forecast growth used by the DCF.
    div = inputs["dividend_rate"]
    if div and div > 0 and rate > tg:
        est["dividend_discount"] = gordon_growth_value(div * (1.0 + tg), rate, tg)
    else:
        est["dividend_discount"] = None

    # 4. P/E multiple ----------------------------------------------------- #
    fair_pe = args.pe if args.pe is not None else inputs["trailing_pe"]
    used["pe"] = fair_pe
    used["pe_source"] = "user-supplied" if args.pe is not None else "current trailing P/E"
    if eps and eps > 0 and fair_pe and fair_pe > 0:
        est["pe_multiple"] = multiple_value(eps, fair_pe)
    else:
        est["pe_multiple"] = None

    # 5. Graham earnings multiple: EPS x (8.5 + 2g) ---------------------- #
    graham_pe = 8.5 + 2.0 * (growth * 100.0)
    if eps and eps > 0 and graham_pe > 0:
        graham_pe = min(graham_pe, GRAHAM_PE_CAP)
        used["graham_pe"] = graham_pe
        est["graham"] = multiple_value(eps, graham_pe)
    else:
        # 8.5 + 2g <= 0 means the growth assumption is below -4.25%/yr; the
        # Graham formula is out of its useful domain, so skip it.
        used["graham_pe"] = None
        est["graham"] = None

    # 6. EV/EBITDA multiple -------------------------------------------- #
    ebitda = inputs["ebitda"]
    fair_ev_ebitda = args.ev_ebitda if args.ev_ebitda is not None else inputs["ev_to_ebitda"]
    used["ev_ebitda"] = fair_ev_ebitda
    used["ev_ebitda_source"] = (
        "user-supplied" if args.ev_ebitda is not None else "current EV/EBITDA"
    )
    if ebitda and ebitda > 0 and fair_ev_ebitda and fair_ev_ebitda > 0 and shares and shares > 0:
        est["ev_ebitda_multiple"] = ev_multiple_value(
            ebitda, fair_ev_ebitda, net_debt, shares
        )
    else:
        est["ev_ebitda_multiple"] = None

    # 7. P/S multiple ------------------------------------------------ #
    rps = inputs["revenue_per_share"]
    fair_ps = args.ps if args.ps is not None else inputs["price_to_sales"]
    used["ps"] = fair_ps
    used["ps_source"] = "user-supplied" if args.ps is not None else "current P/S"
    if rps and rps > 0 and fair_ps and fair_ps > 0:
        est["ps_multiple"] = multiple_value(rps, fair_ps)
    else:
        est["ps_multiple"] = None

    # 8. Reported enterprise value -> equity per share (consistency check) - #
    ev = inputs["enterprise_value"]
    if ev and shares and shares > 0:
        est["ev_reported_to_equity"] = equity_from_enterprise(ev, net_debt, shares)
    else:
        est["ev_reported_to_equity"] = None

    return est, used


# --------------------------------------------------------------------------- #
# Output                                                                       #
# --------------------------------------------------------------------------- #
def _fmt_big(value):
    if value is None:
        return "-"
    magnitude = abs(value)
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if magnitude >= size:
            return f"{value / size:,.2f}{unit}"
    return f"{value:,.2f}"


def _fmt_pct(value, places=2):
    return "-" if value is None else f"{value * 100:.{places}f}%"


def _fmt_money(value):
    return "-" if value is None else f"{value:,.2f}"


def build_report(symbol, inputs, assumptions, estimates, used):
    price = inputs["price"]
    cur = inputs["currency"]
    lines = []

    head = symbol
    if inputs["name"]:
        head += f" - {inputs['name']}"
    venue = " - ".join(b for b in (inputs["exchange"], cur) if b)
    if venue:
        head += f"  ({venue})"
    lines.append(head)
    summary = f"Price {_fmt_money(price)} {cur}".rstrip()
    summary += f"    Market cap {_fmt_big(inputs['market_cap'])}"
    if inputs["sector"]:
        summary += f"    Sector: {inputs['sector']}"
    lines.append(summary)

    lines.append("\nFundamentals (Yahoo Finance, trailing 12 months)")
    rows = [
        ("Free cash flow", _fmt_big(inputs["free_cash_flow"])),
        ("EBITDA", _fmt_big(inputs["ebitda"])),
        ("Revenue", _fmt_big(inputs["revenue"])),
        ("Total debt", _fmt_big(inputs["total_debt"])),
        ("Total cash", _fmt_big(inputs["total_cash"])),
        ("Net debt (- = net cash)", _fmt_big(inputs["net_debt"])),
        ("Shares outstanding", _fmt_big(inputs["shares"])),
        ("EPS (trailing / forward)",
         f"{_fmt_money(inputs['eps_ttm'])} / {_fmt_money(inputs['eps_forward'])}"),
        ("Book value / share", _fmt_money(inputs["book_value_per_share"])),
        ("Revenue / share", _fmt_money(inputs["revenue_per_share"])),
        ("Dividend / share", _fmt_money(inputs["dividend_rate"])),
        ("Beta", _fmt_money(inputs["beta"])),
        ("P/E (trailing / forward)",
         f"{_fmt_money(inputs['trailing_pe'])} / {_fmt_money(inputs['forward_pe'])}"),
        ("EV / EBITDA", _fmt_money(inputs["ev_to_ebitda"])),
        ("P/S (trailing)", _fmt_money(inputs["price_to_sales"])),
        ("Analyst growth (5y / 1y)",
         f"{_fmt_pct(inputs['analyst_growth_5y'])} / {_fmt_pct(inputs['analyst_growth_1y'])}"),
    ]
    for label, value in rows:
        lines.append(f"  {label:<26} {value:>16}")

    notes = assumptions["notes"]
    lines.append("\nAssumptions")
    lines.append(f"  Discount rate    {_fmt_pct(assumptions['discount_rate']):>8}   ({notes['discount_rate']})")
    lines.append(f"  FCF growth       {_fmt_pct(assumptions['growth']):>8}   ({notes['growth']})")
    lines.append(f"  Terminal growth  {_fmt_pct(assumptions['terminal_growth']):>8}")
    lines.append(f"  Forecast years   {assumptions['years']:>8}")

    lines.append("\nIntrinsic value estimates (per share unless noted)")
    lines.append(f"  {'Method':<34}{'Value':>14}{'Price vs est.':>16}")

    def row(label, value, gap=None):
        gap_s = "" if gap is None else f"{gap * 100:+.1f}%"
        lines.append(f"  {label:<34}{_fmt_money(value):>14}{gap_s:>16}")

    row("Two-stage DCF", estimates["dcf_two_stage"],
        _vs_price(price, estimates["dcf_two_stage"]))
    pe = used["pe"]
    row(f"P/E multiple ({_fmt_money(pe)}x)" if pe else "P/E multiple",
        estimates["pe_multiple"], _vs_price(price, estimates["pe_multiple"]))
    gp = used["graham_pe"]
    row(f"Graham EPS x (8.5+2g) ({_fmt_money(gp)}x)" if gp else "Graham EPS x (8.5+2g)",
        estimates["graham"], _vs_price(price, estimates["graham"]))
    ee = used["ev_ebitda"]
    row(f"EV/EBITDA multiple ({_fmt_money(ee)}x)" if ee else "EV/EBITDA multiple",
        estimates["ev_ebitda_multiple"], _vs_price(price, estimates["ev_ebitda_multiple"]))
    ps = used["ps"]
    row(f"P/S multiple ({_fmt_money(ps)}x)" if ps else "P/S multiple",
        estimates["ps_multiple"], _vs_price(price, estimates["ps_multiple"]))

    low_payout = bool(
        inputs["dividend_rate"] and price and inputs["dividend_rate"] / price < 0.01
    )
    row(f"Dividend discount (g={_fmt_pct(assumptions['terminal_growth'])})",
        estimates["dividend_discount"],
        _vs_price(price, estimates["dividend_discount"]))

    implied = estimates["reverse_dcf_implied_growth"]
    tail = (
        f"   (vs assumed {_fmt_pct(assumptions['growth'])})"
        if implied is not None else ""
    )
    lines.append(
        f"  {'Reverse DCF -> implied growth':<34}{_fmt_pct(implied):>14}{'':>16}{tail}"
    )

    row("[check] reported EV -> equity", estimates["ev_reported_to_equity"],
        _vs_price(price, estimates["ev_reported_to_equity"]))

    if low_payout:
        lines.append(
            "  (dividend yield < 1% - the Gordon dividend model is not "
            "meaningful for this stock)"
        )

    lines.append(
        "\nNotes: estimates are only as good as the assumptions - a DCF swings hard on\n"
        "the discount rate, growth and terminal growth. Multiples default to the stock's\n"
        "own current multiple (so that row reproduces the market view) unless you pass a\n"
        "considered --pe / --ev-ebitda / --ps. 'Price vs est.' > 0 means the market price\n"
        "sits above that estimate. Free cash flow is Yahoo's levered TTM figure. The\n"
        "[check] row is Yahoo's reported enterprise value less net debt, per share; it\n"
        "should land near the price, and a wide gap means Yahoo's EV figure is stale."
    )
    return "\n".join(lines)


def build_json(symbol, inputs, assumptions, estimates, used):
    price = inputs["price"]

    def per_share(key):
        value = estimates[key]
        return {"value_per_share": value, "price_vs_estimate": _vs_price(price, value)}

    return {
        "symbol": symbol,
        "name": inputs["name"],
        "exchange": inputs["exchange"],
        "currency": inputs["currency"],
        "sector": inputs["sector"],
        "price": price,
        "inputs": {k: v for k, v in inputs.items()
                   if k not in ("name", "exchange", "currency", "sector", "price")},
        "assumptions": assumptions,
        "multiples_used": used,
        "estimates": {
            "dcf_two_stage": per_share("dcf_two_stage"),
            "reverse_dcf_implied_growth": {
                "implied_growth": estimates["reverse_dcf_implied_growth"],
                "analyst_growth_5y": inputs["analyst_growth_5y"],
            },
            "dividend_discount": per_share("dividend_discount"),
            "pe_multiple": per_share("pe_multiple"),
            "graham": per_share("graham"),
            "ev_ebitda_multiple": per_share("ev_ebitda_multiple"),
            "ps_multiple": per_share("ps_multiple"),
            "ev_reported_to_equity": per_share("ev_reported_to_equity"),
        },
    }


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Estimate a stock's intrinsic value every way valuation.py can, "
        "from Yahoo Finance fundamentals.",
    )
    parser.add_argument(
        "symbol", help="Ticker in Yahoo notation, e.g. AAPL, VOD.L, D05.SI, SAP.DE"
    )
    parser.add_argument(
        "--discount-rate", type=float, metavar="R",
        help="Annual discount rate / WACC as a fraction, e.g. 0.09. "
        "Default: CAPM from the stock's beta, else 0.09",
    )
    parser.add_argument(
        "--growth", type=float, metavar="G",
        help="Forecast-stage annual FCF growth as a fraction, e.g. 0.08. "
        "Default: the analyst 5-year EPS growth estimate, else 0.05",
    )
    parser.add_argument(
        "--terminal-growth", type=float, default=DEFAULT_TERMINAL_GROWTH, metavar="G",
        help=f"Perpetual growth past the forecast (default: {DEFAULT_TERMINAL_GROWTH})",
    )
    parser.add_argument(
        "--years", type=positive_int, default=DEFAULT_YEARS, metavar="N",
        help=f"Explicit DCF forecast horizon in years (default: {DEFAULT_YEARS})",
    )
    parser.add_argument(
        "--risk-free", type=float, default=DEFAULT_RISK_FREE, metavar="R",
        help=f"Risk-free rate for the CAPM discount rate (default: {DEFAULT_RISK_FREE})",
    )
    parser.add_argument(
        "--equity-risk-premium", type=float, default=DEFAULT_ERP, metavar="P",
        help=f"Equity risk premium for the CAPM discount rate (default: {DEFAULT_ERP})",
    )
    parser.add_argument(
        "--pe", type=float, metavar="X",
        help="Fair trailing P/E for the multiple valuation "
        "(default: the stock's current trailing P/E)",
    )
    parser.add_argument(
        "--ev-ebitda", type=float, metavar="X",
        help="Fair EV/EBITDA for the multiple valuation "
        "(default: the stock's current EV/EBITDA)",
    )
    parser.add_argument(
        "--ps", type=float, metavar="X",
        help="Fair trailing P/S for the multiple valuation "
        "(default: the stock's current P/S)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        modules = fetch_fundamentals(args.symbol)
    except (requests.RequestException, ValueError, KeyError) as exc:
        die(f"failed to fetch fundamentals for {args.symbol!r}: {exc}", args.json)

    inputs = collect_inputs(modules)
    if inputs["price"] is None:
        die(f"no usable fundamentals returned for {args.symbol!r}", args.json)

    assumptions = resolve_assumptions(inputs, args)
    estimates, used = compute_estimates(inputs, assumptions, args)
    symbol = args.symbol.upper()

    if args.json:
        print(json.dumps(build_json(symbol, inputs, assumptions, estimates, used), indent=2))
    else:
        print(build_report(symbol, inputs, assumptions, estimates, used))


if __name__ == "__main__":
    main()
