#!/usr/bin/env python3
"""
Retrieve a stock's fundamental indicators from Yahoo Finance's public
``quoteSummary`` endpoint. No API key or authentication required (a cookie +
crumb are fetched automatically, via stock_intrinsic_value.py's fetch).

Give it a ticker in Yahoo's notation (AAPL, VOD.L, D05.SI, SAP.DE, ...). The
script reports, in six groups:

- profitability       gross / operating / net margin, ROE, ROA
- growth              revenue and earnings growth (YoY, latest quarter),
                      analyst 5-year growth estimate
- valuation           trailing / forward P/E, PEG, EV/EBITDA, P/B, P/S,
                      free-cash-flow yield
- financial health    debt/equity, net debt/EBITDA, current and quick ratio
- cash flow           free and operating cash flow, cash conversion
- shareholder returns dividend yield, payout ratio

Most figures are read as Yahoo reports them; PEG, FCF yield, net
debt/EBITDA, cash conversion and dividend yield are derived. An indicator
Yahoo leaves out, or that isn't meaningful (e.g. PEG with negative growth),
is reported as missing. extract_indicators() is also imported by the stock
information web app (app/stock_information/). Supports --json for structured
output. On failure the process exits non-zero and prints {"error": "..."} to
stderr.
"""

import argparse
import json

import requests

import stock_intrinsic_value as siv
from cli_utils import die

# (group, [(indicator key, label, format)]) in display order. Formats:
# "pct" = a fraction shown as a percentage, "ratio" = a plain number,
# "big" = a currency amount abbreviated K/M/B/T.
INDICATOR_GROUPS = [
    ("Profitability", [
        ("gross_margin", "Gross margin", "pct"),
        ("operating_margin", "Operating margin", "pct"),
        ("net_margin", "Net margin", "pct"),
        ("return_on_equity", "Return on equity (ROE)", "pct"),
        ("return_on_assets", "Return on assets (ROA)", "pct"),
    ]),
    ("Growth", [
        ("revenue_growth", "Revenue growth (YoY)", "pct"),
        ("earnings_growth", "Earnings growth (YoY)", "pct"),
        ("analyst_growth_5y", "Analyst 5-year growth estimate", "pct"),
    ]),
    ("Valuation", [
        ("trailing_pe", "P/E (trailing)", "ratio"),
        ("forward_pe", "P/E (forward)", "ratio"),
        ("peg", "PEG (trailing P/E / 5y growth)", "ratio"),
        ("ev_to_ebitda", "EV/EBITDA", "ratio"),
        ("price_to_book", "P/B", "ratio"),
        ("price_to_sales", "P/S (trailing)", "ratio"),
        ("fcf_yield", "Free-cash-flow yield", "pct"),
    ]),
    ("Financial health", [
        ("debt_to_equity", "Debt/equity", "ratio"),
        ("net_debt_to_ebitda", "Net debt/EBITDA", "ratio"),
        ("current_ratio", "Current ratio", "ratio"),
        ("quick_ratio", "Quick ratio", "ratio"),
    ]),
    ("Cash flow", [
        ("free_cash_flow", "Free cash flow", "big"),
        ("operating_cash_flow", "Operating cash flow", "big"),
        ("cash_conversion", "Cash conversion (FCF / net income)", "ratio"),
    ]),
    ("Shareholder returns", [
        ("dividend_yield", "Dividend yield", "pct"),
        ("payout_ratio", "Payout ratio", "pct"),
    ]),
]


# --------------------------------------------------------------------------- #
# Indicators                                                                   #
# --------------------------------------------------------------------------- #
def _ratio(numerator, denominator):
    """numerator / denominator, or None unless both are present and the denominator is positive."""
    if numerator is None or not denominator or denominator <= 0:
        return None
    return numerator / denominator


def extract_indicators(modules, inputs):
    """Pull the fundamental indicators from the quoteSummary ``modules``.

    ``inputs`` is stock_intrinsic_value.collect_inputs() of the same modules;
    figures it already parsed are reused rather than read twice. Margins,
    returns, growth rates and yields are fractions (0.25 == 25%); multiples
    and ratios are plain numbers. Anything Yahoo leaves out, or that isn't
    meaningful (e.g. PEG with negative growth), is None.
    """
    def num(module, key):
        return siv._num(modules, module, key)

    trailing_pe = inputs["trailing_pe"]
    growth_5y = inputs["analyst_growth_5y"]
    peg = (
        _ratio(trailing_pe, growth_5y * 100.0)
        if trailing_pe and trailing_pe > 0 and growth_5y is not None
        else None
    )
    # Yahoo reports debt/equity as a percentage (150.0 == 1.5x).
    debt_to_equity = num("financialData", "debtToEquity")
    # Yahoo reports a gross margin of exactly 0 for banks and others with no
    # cost of goods sold; that means "not applicable", not a 0% margin.
    gross_margin = num("financialData", "grossMargins") or None
    fcf = inputs["free_cash_flow"]
    return {
        "gross_margin": gross_margin,
        "operating_margin": num("financialData", "operatingMargins"),
        "net_margin": num("financialData", "profitMargins"),
        "return_on_equity": num("financialData", "returnOnEquity"),
        "return_on_assets": num("financialData", "returnOnAssets"),
        "revenue_growth": num("financialData", "revenueGrowth"),
        "earnings_growth": num("financialData", "earningsGrowth"),
        "analyst_growth_5y": growth_5y,
        "trailing_pe": trailing_pe,
        "forward_pe": inputs["forward_pe"],
        "peg": peg,
        "ev_to_ebitda": inputs["ev_to_ebitda"],
        "price_to_book": num("defaultKeyStatistics", "priceToBook"),
        "price_to_sales": inputs["price_to_sales"],
        "fcf_yield": _ratio(fcf, inputs["market_cap"]),
        "debt_to_equity": None if debt_to_equity is None else debt_to_equity / 100.0,
        "net_debt_to_ebitda": _ratio(inputs["net_debt"], inputs["ebitda"]),
        "current_ratio": num("financialData", "currentRatio"),
        "quick_ratio": num("financialData", "quickRatio"),
        "free_cash_flow": fcf,
        "operating_cash_flow": num("financialData", "operatingCashflow"),
        "cash_conversion": _ratio(fcf, num("defaultKeyStatistics", "netIncomeToCommon")),
        "dividend_yield": _ratio(inputs["dividend_rate"], inputs["price"]),
        "payout_ratio": num("summaryDetail", "payoutRatio"),
    }


# --------------------------------------------------------------------------- #
# Output                                                                       #
# --------------------------------------------------------------------------- #
def _fmt(value, kind):
    if kind == "pct":
        return siv._fmt_pct(value)
    if kind == "big":
        return siv._fmt_big(value)
    return siv._fmt_money(value)


def build_report(symbol, inputs, indicators):
    cur = inputs["currency"]
    lines = []

    head = symbol
    if inputs["name"]:
        head += f" - {inputs['name']}"
    venue = " - ".join(b for b in (inputs["exchange"], cur) if b)
    if venue:
        head += f"  ({venue})"
    lines.append(head)
    summary = f"Price {siv._fmt_money(inputs['price'])} {cur}".rstrip()
    summary += f"    Market cap {siv._fmt_big(inputs['market_cap'])}"
    if inputs["sector"]:
        summary += f"    Sector: {inputs['sector']}"
    if inputs["industry"]:
        summary += f"    Industry: {inputs['industry']}"
    lines.append(summary)

    for group, rows in INDICATOR_GROUPS:
        lines.append(f"\n{group}")
        for key, label, kind in rows:
            lines.append(f"  {label:<36} {_fmt(indicators[key], kind):>14}")

    lines.append(
        "\nNotes: trailing-12-month figures from Yahoo Finance as reported; growth is\n"
        "year over year for the latest quarter. '-' means not reported, or not\n"
        "meaningful (e.g. PEG with negative growth, cash conversion with a net loss).\n"
        "Amounts are in the listing currency. Descriptive, not a forecast or advice."
    )
    return "\n".join(lines)


def build_json(symbol, inputs, indicators):
    return {
        "symbol": symbol,
        "name": inputs["name"],
        "exchange": inputs["exchange"],
        "currency": inputs["currency"],
        "sector": inputs["sector"],
        "industry": inputs["industry"],
        "price": inputs["price"],
        "market_cap": inputs["market_cap"],
        "indicators": indicators,
    }


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Retrieve a stock's fundamental indicators from Yahoo Finance.",
    )
    parser.add_argument(
        "symbol", help="Ticker in Yahoo notation, e.g. AAPL, VOD.L, D05.SI, SAP.DE"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        modules = siv.fetch_fundamentals(args.symbol)
    except (requests.RequestException, ValueError, KeyError) as exc:
        die(f"failed to fetch fundamentals for {args.symbol!r}: {exc}", args.json)

    inputs = siv.collect_inputs(modules)
    if inputs["price"] is None:
        die(f"no usable fundamentals returned for {args.symbol!r}", args.json)

    indicators = extract_indicators(modules, inputs)
    symbol = args.symbol.upper()

    if args.json:
        print(json.dumps(build_json(symbol, inputs, indicators), indent=2))
    else:
        print(build_report(symbol, inputs, indicators))


if __name__ == "__main__":
    main()
