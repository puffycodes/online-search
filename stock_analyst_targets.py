#!/usr/bin/env python3
"""
Retrieve a stock's analyst price targets and recommendations from Yahoo
Finance's public ``quoteSummary`` endpoint. No API key or authentication
required (a cookie + crumb are fetched automatically, via
yahoo_finance.fetch_quote_summary()).

Give it a ticker in Yahoo's notation (AAPL, VOD.L, D05.SI, SAP.DE, ...). The
script reports:

- price targets       the analysts' low / median / mean / high 12-month
                      target, each with its upside or downside versus the
                      current price
- consensus           Yahoo's recommendation key (strong buy ... sell) and
                      its mean score on a 1 (strong buy) to 5 (strong sell)
                      scale, with the number of analysts behind the targets
- recommendation trend  strong buy / buy / hold / sell / strong sell counts
                      for this month and each of the previous three
- analyst actions     each firm's upgrade, downgrade, initiation or
                      reiteration and target change over the last --days
                      days (default 90), newest first

These are other people's opinions as Yahoo aggregates them, not a forecast
this script makes. Only covered company stocks have them; an ETF, index,
currency or future fails with "no analyst coverage". Supports --json for
structured output. On failure the process exits non-zero and prints
{"error": "..."} to stderr.
"""

import argparse
import json
from datetime import datetime, timezone

import requests

import yahoo_finance as yf
from cli_utils import die, positive_int, use_utf8_output
from stock_intrinsic_value import _fmt_money

MODULES = ["price", "financialData", "recommendationTrend", "upgradeDowngradeHistory"]
DEFAULT_DAYS = 90

TARGETS = [("low", "Low"), ("median", "Median"), ("mean", "Mean"), ("high", "High")]
RATINGS = [
    ("strong_buy", "strongBuy", "Strong buy"),
    ("buy", "buy", "Buy"),
    ("hold", "hold", "Hold"),
    ("sell", "sell", "Sell"),
    ("strong_sell", "strongSell", "Strong sell"),
]
ACTIONS = {"up": "upgrade", "down": "downgrade", "init": "initiate",
           "reit": "reiterate", "main": "maintain"}
TARGET_ACTIONS = {"Raises": "raised", "Lowers": "lowered", "Maintains": "maintained",
                  "Announces": "announced", "Adjusts": "adjusted"}
PERIOD_LABELS = {"0m": "This month", "-1m": "1 month ago", "-2m": "2 months ago", "-3m": "3 months ago"}


# --------------------------------------------------------------------------- #
# Parse                                                                        #
# --------------------------------------------------------------------------- #
def recommendation_trend(modules):
    """Rating counts per month from ``recommendationTrend``, newest first."""
    rows = []
    for entry in (modules.get("recommendationTrend") or {}).get("trend") or []:
        counts = {key: yf.summary_num(entry, raw) for key, raw, _ in RATINGS}
        if all(v is None for v in counts.values()):
            continue
        counts = {key: int(v or 0) for key, v in counts.items()}
        rows.append({"period": entry.get("period"), **counts, "total": sum(counts.values())})
    order = {p: i for i, p in enumerate(PERIOD_LABELS)}
    rows.sort(key=lambda r: order.get(r["period"], len(order)))
    return rows


def _positive(value):
    """A price target, or None for Yahoo's 0 placeholder (no target given)."""
    return value if isinstance(value, (int, float)) and value > 0 else None


def analyst_actions(modules, days=DEFAULT_DAYS, now=None):
    """Firm-level actions from ``upgradeDowngradeHistory`` in the last ``days``.

    Newest first. ``action`` is upgrade / downgrade / initiate / reiterate /
    maintain; ``target_action`` is raised / lowered / maintained / announced /
    adjusted, or None when the firm gave no target. ``now`` (epoch seconds)
    is for tests.
    """
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    cutoff = now - days * 86400
    dated = []
    for entry in (modules.get("upgradeDowngradeHistory") or {}).get("history") or []:
        epoch = entry.get("epochGradeDate")
        if not isinstance(epoch, (int, float)) or epoch < cutoff:
            continue
        action = entry.get("action")
        target_action = entry.get("priceTargetAction")
        dated.append((epoch, {
            "date": datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d"),
            "firm": entry.get("firm") or None,
            "action": ACTIONS.get(action, action or None),
            "from_grade": entry.get("fromGrade") or None,
            "to_grade": entry.get("toGrade") or None,
            "target_action": TARGET_ACTIONS.get(target_action, (target_action or "").lower() or None),
            "target": _positive(entry.get("currentPriceTarget")),
            "prior_target": _positive(entry.get("priorPriceTarget")),
        }))
    dated.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in dated]


def action_summary(actions):
    """Counts of rating changes and target moves among ``actions``."""
    def count(key, value):
        return sum(1 for a in actions if a[key] == value)

    return {
        "upgrades": count("action", "upgrade"),
        "downgrades": count("action", "downgrade"),
        "initiations": count("action", "initiate"),
        "targets_raised": count("target_action", "raised"),
        "targets_lowered": count("target_action", "lowered"),
    }


def extract_targets(modules, days=DEFAULT_DAYS, now=None):
    """Flatten the raw modules into the JSON-shaped targets dict.

    ``upside`` is each target's distance from the price as a fraction
    (0.10 == the target is 10% above the price); None without a price.
    """
    def fd(key):
        return yf.summary_num(modules, "financialData", key)

    price = fd("currentPrice") or yf.summary_num(modules, "price", "regularMarketPrice")
    targets = {key: fd(f"target{label}Price") for key, label in TARGETS}
    upside = {
        key: round(value / price - 1, 4) if value is not None and price else None
        for key, value in targets.items()
    }
    analysts = fd("numberOfAnalystOpinions")
    key = yf.summary_text(modules, "financialData", "recommendationKey")
    actions = analyst_actions(modules, days, now)
    return {
        "name": yf.summary_text(modules, "price", "longName")
        or yf.summary_text(modules, "price", "shortName"),
        "exchange": yf.summary_text(modules, "price", "exchangeName"),
        "currency": yf.summary_text(modules, "price", "currency") or "",
        "price": price,
        "analysts": None if analysts is None else int(analysts),
        "targets": targets,
        "upside": upside,
        "recommendation": {
            "key": None if key in (None, "none") else key,
            "mean": fd("recommendationMean"),
        },
        "trend": recommendation_trend(modules),
        "actions_days": days,
        "action_summary": action_summary(actions),
        "actions": actions,
    }


def has_coverage(data):
    return (
        any(v is not None for v in data["targets"].values())
        or data["recommendation"]["key"] is not None
        or bool(data["trend"])
        or bool(data["actions"])
    )


# --------------------------------------------------------------------------- #
# Output                                                                       #
# --------------------------------------------------------------------------- #
def _fmt_signed_pct(value):
    return "-" if value is None else f"{value * 100:+.2f}%"


def build_report(symbol, data):
    cur = data["currency"]
    lines = []
    head = symbol
    if data["name"]:
        head += f" - {data['name']}"
    venue = " - ".join(b for b in (data["exchange"], cur) if b)
    if venue:
        head += f"  ({venue})"
    lines.append(head)
    summary = f"Price {_fmt_money(data['price'])} {cur}".rstrip()
    if data["analysts"] is not None:
        summary += f"    {data['analysts']} analysts with a price target"
    lines.append(summary)

    lines.append(f"\n{'Price targets':<20} {'Target':>12} {'vs price':>10}")
    for key, label in TARGETS:
        lines.append(
            f"  {label:<18} {_fmt_money(data['targets'][key]):>12} "
            f"{_fmt_signed_pct(data['upside'][key]):>10}"
        )

    rec = data["recommendation"]
    lines.append("")
    if rec["key"] is None and rec["mean"] is None:
        lines.append("Consensus  -")
    else:
        text = (rec["key"] or "-").replace("_", " ").upper()
        if rec["mean"] is not None:
            text += f"  (mean {rec['mean']:.2f} on 1 = strong buy ... 5 = strong sell)"
        lines.append(f"Consensus  {text}")

    lines.append("\nRecommendation trend")
    if not data["trend"]:
        lines.append("  No rating counts from Yahoo")
    else:
        header = f"  {'':<14}" + "".join(f"{label:>12}" for _, _, label in RATINGS) + f"{'Total':>8}"
        lines.append(header)
        for row in data["trend"]:
            label = PERIOD_LABELS.get(row["period"], row["period"] or "?")
            lines.append(
                f"  {label:<14}" + "".join(f"{row[key]:>12}" for key, _, _ in RATINGS)
                + f"{row['total']:>8}"
            )

    days = data["actions_days"]
    lines.append(f"\nAnalyst actions (last {days} days)")
    if not data["actions"]:
        lines.append(f"  No upgrades, downgrades or target changes from Yahoo in the last {days} days")
    else:
        s = data["action_summary"]
        lines.append(
            f"  {s['upgrades']} upgrades, {s['downgrades']} downgrades, "
            f"{s['initiations']} initiations; "
            f"targets raised {s['targets_raised']}, lowered {s['targets_lowered']}"
        )
        lines.append(f"  {'Date':<11} {'Firm':<22} {'Action':<10} {'Rating':<28} Target")
        for a in data["actions"]:
            rating = a["to_grade"] or "-"
            if a["from_grade"] and a["from_grade"] != a["to_grade"]:
                rating = f"{a['from_grade']} -> {rating}"
            target = "-"
            if a["target"] is not None:
                target = _fmt_money(a["target"])
                if a["prior_target"] is not None and a["prior_target"] != a["target"]:
                    target = f"{_fmt_money(a['prior_target'])} -> {target}"
            firm = (a["firm"] or "?")[:22]
            lines.append(
                f"  {a['date']:<11} {firm:<22} {a['action'] or '-':<10} {rating:<28} {target}"
            )

    lines.append(
        "\nNotes: analyst opinions as aggregated by Yahoo Finance; targets are\n"
        "12-month price targets in the trading currency. The trend counts\n"
        "ratings, which can cover more analysts than set a price target.\n"
        "Action dates are UTC; Yahoo lists actions for US listings only.\n"
        "Other people's opinions, not a forecast or advice."
    )
    return "\n".join(lines)


def build_json(symbol, data):
    return {"symbol": symbol, **data}


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Retrieve a stock's analyst price targets and recommendations from Yahoo Finance.",
    )
    parser.add_argument(
        "symbol", help="Ticker in Yahoo notation, e.g. AAPL, VOD.L, D05.SI, SAP.DE"
    )
    parser.add_argument(
        "--days", type=positive_int, default=DEFAULT_DAYS,
        help=f"Days of analyst upgrades, downgrades and target changes to list "
             f"(default {DEFAULT_DAYS}).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    try:
        modules = yf.fetch_quote_summary(args.symbol, MODULES)
    except (requests.RequestException, ValueError, KeyError) as exc:
        die(f"failed to fetch analyst targets for {args.symbol!r}: {exc}", args.json)

    data = extract_targets(modules, args.days)
    if not has_coverage(data):
        die(
            f"no analyst coverage for {args.symbol!r} (only covered company stocks have targets)",
            args.json,
        )

    symbol = args.symbol.upper()
    if args.json:
        print(json.dumps(build_json(symbol, data), indent=2))
    else:
        print(build_report(symbol, data))


if __name__ == "__main__":
    main()
