#!/usr/bin/env python3
"""
Fetch the past price history of a single stock from Yahoo Finance's public
chart endpoint and render it as a candlestick chart with matplotlib. No API
key or authentication required.

Give it a ticker in Yahoo's notation (AAPL, VOD.L, D05.SI, SAP.DE, ...) and
either a --range keyword, an explicit --start/--end window, or --last N to
plot just the most recent N sessions. Pick the bar size with --interval
(1d, 1wk, 1mo).

By default the chart is written to <SYMBOL>_candlestick.png; use --output to
change the path or --show to open an interactive window instead. Add
--volume for a volume panel beneath the price panel.

On failure the process exits non-zero and prints an error to stderr.
"""

import argparse
import datetime as dt
import sys

import requests

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# Yahoo rejects requests without a browser-like User-Agent.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
REQUEST_TIMEOUT = 15

VALID_RANGES = [
    "5d", "1mo", "3mo", "6mo", "ytd", "1y", "2y", "5y", "10y", "max",
]
VALID_INTERVALS = ["1d", "1wk", "1mo"]
DEFAULT_RANGE = "6mo"
DEFAULT_INTERVAL = "1d"
SECONDS_PER_DAY = 86400

# Up candles are drawn hollow (surface fill) with a green edge; down candles
# are filled solid red. Direction is encoded by BOTH hue and fill, so the
# chart still reads for red/green colour-vision deficiency and in greyscale.
COLOR_UP = "#1a9850"
COLOR_DOWN = "#d73027"
COLOR_WICK = "#333333"
COLOR_GRID = "#d0d0d0"
COLOR_SURFACE = "#ffffff"


def _parse_date(value):
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise ValueError(f"invalid date {value!r}, expected YYYY-MM-DD")


def build_params(args):
    """Return the query params for the chart call from the parsed args."""
    params = {"interval": args.interval, "includeAdjustedClose": "true"}

    if args.start or args.end:
        start = _parse_date(args.start) if args.start else None
        end = _parse_date(args.end) if args.end else dt.datetime.now(dt.timezone.utc)
        if start is None:
            raise ValueError("--end requires --start")
        if end <= start:
            raise ValueError("--end must be after --start")
        params["period1"] = int(start.timestamp())
        # pad the end by a day so the final session is inclusive
        params["period2"] = int(end.timestamp()) + SECONDS_PER_DAY
    elif args.last:
        # Fetch a generous calendar window, then trim to the last N bars.
        # ~1.6 calendar days per trading day, plus slack for holidays.
        lookback_days = args.last * 2 + 10
        if args.interval == "1wk":
            lookback_days = args.last * 9 + 14
        elif args.interval == "1mo":
            lookback_days = args.last * 32 + 31
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)
        params["period1"] = int(start.timestamp())
        params["period2"] = int(dt.datetime.now(dt.timezone.utc).timestamp()) + SECONDS_PER_DAY
    else:
        params["range"] = args.range

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


def extract_rows(result):
    """Return (meta, rows) where each row is a dict with date + OHLCV."""
    meta = result.get("meta", {})
    gmtoffset = meta.get("gmtoffset", 0) or 0
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    rows = []
    for i, ts in enumerate(timestamps):
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        low = lows[i] if i < len(lows) else None
        c = closes[i] if i < len(closes) else None
        if None in (o, h, low, c):
            # In-progress bar or a data gap - skip it.
            continue
        date = dt.datetime.utcfromtimestamp(ts + gmtoffset)
        volume = volumes[i] if i < len(volumes) else None
        rows.append(
            {
                "date": date,
                "open": o,
                "high": h,
                "low": low,
                "close": c,
                "volume": int(volume) if volume is not None else None,
            }
        )
    return meta, rows


def render_chart(symbol, exchange, currency, interval, rows, out_path, show, with_volume):
    import matplotlib

    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    n = len(rows)
    xs = list(range(n))
    dates = [r["date"] for r in rows]

    if with_volume:
        fig, (ax, ax_vol) = plt.subplots(
            2, 1, figsize=(max(8, n * 0.11), 7), sharex=True,
            gridspec_kw={"height_ratios": [3, 1]}, constrained_layout=True,
        )
    else:
        fig, ax = plt.subplots(
            figsize=(max(8, n * 0.11), 6), constrained_layout=True,
        )
        ax_vol = None

    fig.patch.set_facecolor(COLOR_SURFACE)
    ax.set_facecolor(COLOR_SURFACE)

    # Candle body half-width in x-units. Slightly narrower for dense charts.
    half_w = 0.3

    for x, r in zip(xs, rows):
        rising = r["close"] >= r["open"]
        edge = COLOR_UP if rising else COLOR_DOWN
        face = COLOR_SURFACE if rising else COLOR_DOWN

        # Wick: a thin line from low to high.
        ax.vlines(x, r["low"], r["high"], color=COLOR_WICK, linewidth=0.8, zorder=2)

        # Body: open-to-close rectangle. Guard against a zero-height doji.
        body_low = min(r["open"], r["close"])
        body_h = abs(r["close"] - r["open"])
        if body_h == 0:
            ax.hlines(r["open"], x - half_w, x + half_w, color=edge, linewidth=1.0, zorder=3)
        else:
            ax.add_patch(
                Rectangle(
                    (x - half_w, body_low), half_w * 2, body_h,
                    facecolor=face, edgecolor=edge, linewidth=0.8, zorder=3,
                )
            )

    ax.set_xlim(-1, n)
    ax.margins(y=0.05)
    ax.grid(True, color=COLOR_GRID, linewidth=0.5, alpha=0.7)
    ax.set_axisbelow(True)
    ax.set_ylabel(f"Price ({currency})" if currency else "Price")

    span = f"{dates[0]:%Y-%m-%d} → {dates[-1]:%Y-%m-%d}" if n else ""
    title_bits = [b for b in (symbol, exchange) if b and b != "?"]
    ax.set_title(
        f"{'  ·  '.join(title_bits)}\n{n} {interval} bars   {span}",
        fontsize=12, loc="left",
    )

    def fmt_date(value, _pos):
        idx = int(round(value))
        if 0 <= idx < n:
            return dates[idx].strftime("%Y-%m-%d" if interval != "1mo" else "%Y-%m")
        return ""

    target = ax_vol if ax_vol is not None else ax
    target.xaxis.set_major_locator(MaxNLocator(nbins=10, integer=True, prune="both"))
    target.xaxis.set_major_formatter(FuncFormatter(fmt_date))
    for label in target.get_xticklabels():
        label.set_rotation(45)
        label.set_horizontalalignment("right")

    if ax_vol is not None:
        ax_vol.set_facecolor(COLOR_SURFACE)
        for x, r in zip(xs, rows):
            if r["volume"] is None:
                continue
            rising = r["close"] >= r["open"]
            ax_vol.bar(
                x, r["volume"], width=half_w * 2,
                color=(COLOR_UP if rising else COLOR_DOWN), alpha=0.75, linewidth=0,
            )
        ax_vol.set_xlim(-1, n)
        ax_vol.grid(True, color=COLOR_GRID, linewidth=0.5, alpha=0.7)
        ax_vol.set_axisbelow(True)
        ax_vol.set_ylabel("Volume")
        def fmt_volume(v, _pos):
            if v >= 1e9:
                return f"{v / 1e9:.1f}B"
            if v >= 1e6:
                return f"{v / 1e6:.0f}M"
            if v >= 1e3:
                return f"{v / 1e3:.0f}K"
            return f"{v:.0f}"

        ax_vol.yaxis.set_major_formatter(FuncFormatter(fmt_volume))

    # Legend: hollow = up (close >= open), filled = down.
    up_key = Rectangle((0, 0), 1, 1, facecolor=COLOR_SURFACE, edgecolor=COLOR_UP)
    down_key = Rectangle((0, 0), 1, 1, facecolor=COLOR_DOWN, edgecolor=COLOR_DOWN)
    ax.legend(
        [up_key, down_key], ["Close ≥ Open", "Close < Open"],
        loc="best", fontsize=9, framealpha=0.9,
    )

    if show:
        plt.show()
    else:
        fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
        print(f"Wrote {out_path}")
    plt.close(fig)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Plot a candlestick chart of a stock's past prices (matplotlib).",
    )
    parser.add_argument(
        "symbol",
        help="Ticker in Yahoo notation, e.g. AAPL, VOD.L, D05.SI, SAP.DE",
    )
    window = parser.add_mutually_exclusive_group()
    window.add_argument(
        "--range",
        choices=VALID_RANGES,
        default=DEFAULT_RANGE,
        help=f"Look-back window (default: {DEFAULT_RANGE})",
    )
    window.add_argument(
        "--last",
        type=int,
        metavar="N",
        help="Plot only the most recent N bars",
    )
    parser.add_argument("--start", help="Start date YYYY-MM-DD (with optional --end)")
    parser.add_argument("--end", help="End date YYYY-MM-DD (defaults to today)")
    parser.add_argument(
        "--interval",
        choices=VALID_INTERVALS,
        default=DEFAULT_INTERVAL,
        help=f"Bar size (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "-o", "--output",
        help="PNG path to write (default: <SYMBOL>_candlestick.png)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open an interactive window instead of writing a file",
    )
    parser.add_argument(
        "--volume",
        action="store_true",
        help="Add a volume panel beneath the price panel",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.last is not None and args.last < 1:
        print("Error: --last must be a positive integer", file=sys.stderr)
        sys.exit(1)

    try:
        params = build_params(args)
        result = fetch_history(args.symbol, params)
        meta, rows = extract_rows(result)
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"Error: failed to fetch prices for {args.symbol!r}: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.last:
        rows = rows[-args.last:]

    if not rows:
        print(f"Error: no price data found for {args.symbol!r}", file=sys.stderr)
        sys.exit(1)

    symbol = meta.get("symbol", args.symbol)
    exchange = meta.get("fullExchangeName") or meta.get("exchangeName") or "?"
    currency = meta.get("currency") or ""
    out_path = args.output or f"{symbol.replace('.', '_')}_candlestick.png"

    try:
        render_chart(
            symbol, exchange, currency, args.interval, rows,
            out_path, args.show, args.volume,
        )
    except ImportError:
        print("Error: matplotlib is required (pip install matplotlib)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
