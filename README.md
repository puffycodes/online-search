# online-search

Small standalone scripts that pull live data from public web APIs. Each is self-contained — no local package, just a `.py` file (the two `stock_*` scripts also share `yahoo_finance.py`, a helper module in the same directory).

- [`hottest_tech_discussions.py`](#hottest_tech_discussionspy) — top 10 hottest Hacker News discussions
- [`market_top_volume.py`](#market_top_volumepy) — top movers (volume, gainers, or losers) on any of ~20 world markets
- [`stock_close_history.py`](#stock_close_historypy) — past daily open / high / low / close prices for a single stock
- [`stock_candlestick.py`](#stock_candlestickpy) — candlestick (OHLC) price chart for a single stock, with moving-average overlays, rendered to a PNG with matplotlib
- [`yahoo_finance.py`](#yahoo_financepy) — shared helper module for the two `stock_*` scripts: Yahoo Finance chart-endpoint fetch + payload parsing
- [`indicators.py`](#indicatorspy) — dependency-free technical indicators over a price series: `moving_average`, `price_vs_moving_average`, `moving_average_cross`, `trend`
- [`stock_tech_buzz_agent.py`](#stock_tech_buzz_agentpy) — agent combining two of the above: top-volume stocks that are being talked about on Hacker News
- [`.claude/agents/hottest-tech-discussions.md`](#claude-code-agent-hottest-tech-discussions) — Claude Code subagent that calls `hottest_tech_discussions.py` and reports the results in chat
- [`.claude/agents/top-volume-stock.md`](#claude-code-agent-top-volume-stock) — Claude Code subagent that calls `market_top_volume.py` and reports the top movers (volume / gainers / losers) on a named market
- [`.claude/agents/stock-closing-price.md`](#claude-code-agent-stock-closing-price) — Claude Code subagent that calls `stock_close_history.py` and reports a stock's past open / high / low / close prices
- [`.claude/agents/stock-candlestick-chart.md`](#claude-code-agent-stock-candlestick-chart) — Claude Code subagent that calls `stock_candlestick.py` and produces a candlestick chart for a named stock
- [`.claude/agents/stock-trend.md`](#claude-code-agent-stock-trend) — Claude Code subagent that calls `stock_close_history.py` + `indicators.py` and reports whether a named stock is trending up or down

---

## hottest_tech_discussions.py

Prints the 10 hottest technology discussions currently on [Hacker News](https://news.ycombinator.com/), using the public [Hacker News API](https://github.com/HackerNews/API). No API key or authentication required.

### Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/)

```bash
pip install requests
```

### Usage

```bash
python3 hottest_tech_discussions.py [--limit N] [--json]
```

| Flag | Default | Description |
|---|---|---|
| `--limit N` | 10 | Number of stories to return |
| `--json` | off | Print machine-readable JSON to stdout instead of a human-readable report — for calling this script as a tool from an agent or another program |

#### Example output

```
Fetching the hottest technology discussions from Hacker News...

1. Some Story Title
   Score: 512  |  Comments: 234  |  Posted: 2026-08-21 09:15 UTC
   Link: https://example.com/article
   Discussion: https://news.ycombinator.com/item?id=12345678

2. Another Story Title
   Score: 480  |  Comments: 190  |  Posted: 2026-08-21 07:42 UTC
   Link: https://example.com/other-article
   Discussion: https://news.ycombinator.com/item?id=12345679

...
```

#### Tool usage (`--json`)

```bash
python3 hottest_tech_discussions.py --json --limit 2
```

```json
[
  {
    "rank": 1,
    "title": "Some Story Title",
    "score": 512,
    "comments": 234,
    "posted": "2026-08-21 09:15 UTC",
    "url": "https://example.com/article",
    "discussion_url": "https://news.ycombinator.com/item?id=12345678"
  },
  {
    "rank": 2,
    "title": "Another Story Title",
    "score": 480,
    "comments": 190,
    "posted": "2026-08-21 07:42 UTC",
    "url": "https://example.com/other-article",
    "discussion_url": "https://news.ycombinator.com/item?id=12345679"
  }
]
```

With `--json`, the leading progress line is suppressed and results print as a JSON array on stdout. On failure, an exit code of `1` is returned and a JSON object (`{"error": "..."}`) is printed to stderr instead of plain text.

### How it works

1. **Fetch candidate pool** — Calls `topstories.json` on the HN API to get the current top story IDs (already ranked by HN's own hotness algorithm) and takes the first `CANDIDATE_POOL_SIZE` (40) of them.
2. **Fetch story details concurrently** — Uses a `ThreadPoolExecutor` (10 workers) to fetch the full item data (`item/{id}.json`) for each candidate in parallel, since each is a separate HTTP request.
3. **Filter and rank** — Discards anything that failed to fetch or isn't a `story` (e.g. jobs, polls get excluded implicitly since only `type == "story"` is kept), then sorts the remaining stories by `score` descending.
4. **Display top N** — Prints the top 10 (`RESULTS_TO_SHOW`), each with rank, title, score, comment count, posting time (UTC), the external article link, and a link to the HN discussion thread.

### Configuration

These are set as constants near the top of the file — edit them directly to change behavior:

| Constant | Default | Description |
|---|---|---|
| `CANDIDATE_POOL_SIZE` | 40 | Number of top stories to fetch details for before ranking |
| `RESULTS_TO_SHOW` | 10 | Number of stories to display |
| `REQUEST_TIMEOUT` | 10 | Per-request timeout in seconds |

### API reference

- Functions and script structure are documented via a docstring at the top of the file and inline comments explaining non-obvious choices (e.g. why `CANDIDATE_POOL_SIZE` is 40).
- `fetch_json(url)` — GETs a URL and returns parsed JSON, raising on HTTP errors.
- `fetch_story(item_id)` — Fetches a single HN item by ID; returns `None` on any request or parsing failure instead of raising (so one bad story doesn't kill the whole batch).
- `get_hottest_tech_discussions(limit=10)` — Orchestrates fetching, filtering, and ranking; returns a list of raw HN story dicts.
- `discussion_url(story)` / `posted_at(story)` — Small helpers: the `news.ycombinator.com/item?id=…` comments URL, and the submission time as a `YYYY-MM-DD HH:MM UTC` string. Also reused by [`stock_tech_buzz_agent.py`](#stock_tech_buzz_agentpy).
- `story_to_dict(rank, story)` — Flattens one raw story into the `{rank, title, score, comments, posted, url, discussion_url}` record used for **both** output modes.
- `format_story(row)` — Renders a `story_to_dict()` record as a multi-line human-readable string.
- `parse_args(argv=None)` — Parses `--limit` and `--json` CLI flags.
- `main(argv=None)` — Entry point; fetches, handles top-level network errors, and prints results (either human-readable or JSON, depending on `--json`).

### Error handling

- If the initial `topstories.json` request fails (network error, timeout, non-2xx response), the script prints an error and exits with status code 1 — plain text on stderr normally, or a JSON object (`{"error": "..."}`) on stderr when `--json` is passed.
- If an individual story's detail fetch fails, that story is silently dropped from consideration rather than aborting the whole run.
- If no stories are found after filtering, the script prints `"No stories found."` (or `[]` with `--json`) and exits normally.

### Notes / limitations

- "Hottest" is defined here as *highest score* among HN's current top stories — it does not itself factor in comment velocity or recency beyond what HN's own top-stories ranking already provides.
- No filtering is applied for "tech" specifically — it relies on Hacker News' general subject matter (predominantly tech) rather than keyword filtering.
- Results reflect a live snapshot; scores and rankings will differ between runs.

---

## market_top_volume.py

Prints the top movers on a stock market you name — the highest-volume stocks, the biggest gainers, or the biggest losers — using [Yahoo Finance](https://finance.yahoo.com/)'s public screeners. No API key or authentication required. It covers ~20 markets across the US, Europe, Asia-Pacific, and the Americas via a `--market` flag, and three ranking metrics via `--metric`.

### Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/)

```bash
pip install requests
```

### Usage

```bash
python3 market_top_volume.py [--market MARKET] [--metric {volume,gainers,losers}] [--limit N] [--json]
```

| Flag | Default | Description |
|---|---|---|
| `--market MARKET` | `us` | Market to query — see the table below |
| `--metric METRIC` | `volume` | Ranking metric: `volume` (most shares traded), `gainers` (biggest % rise), `losers` (biggest % fall) |
| `--limit N` | 10 | Number of stocks to return; use `1` for just the single leader |
| `--json` | off | Print machine-readable JSON to stdout instead of a human-readable report — for calling this script as a tool from an agent or another program |

#### `--metric` values

| Value | Ranks by | US screener | Other markets |
|---|---|---|---|
| `volume` (default) | Most shares traded today | `most_actives` | generic screener sorted by `dayvolume` DESC |
| `gainers` | Largest positive % change | `day_gainers` | generic screener sorted by `percentchange` DESC, with a `dayvolume` floor |
| `losers` | Largest negative % change | `day_losers` | generic screener sorted by `percentchange` ASC, with a `dayvolume` floor |

For `gainers` / `losers`, stocks trading under `MIN_MOVER_VOLUME` (50,000 shares) are dropped so the list isn't swamped by illiquid micro-caps.

#### Supported `--market` values

| Value(s) | Market |
|---|---|
| `us` (default) | Whole US market (NYSE, Nasdaq, NYSE American, …) |
| `nyse` | New York Stock Exchange |
| `nasdaq` | Nasdaq (Global Select + Global Market + Capital Market tiers) |
| `amex` | NYSE American / NYSE Arca |
| `uk`, `lse` | London Stock Exchange |
| `germany`, `xetra` | Deutsche Börse Xetra / Frankfurt |
| `france`, `euronext-paris` | Euronext Paris |
| `netherlands` | Euronext Amsterdam |
| `spain` | Bolsa de Madrid |
| `italy` | Borsa Italiana (Milan) |
| `switzerland` | SIX Swiss Exchange |
| `sweden` | Nasdaq Stockholm |
| `canada`, `tsx` | Toronto Stock Exchange |
| `australia`, `asx` | Australian Securities Exchange |
| `india`, `nse`, `bse` | NSE India / BSE (`india` = both) |
| `hongkong`, `hkex` | Hong Kong Stock Exchange |
| `japan` | Japan Exchange Group (Tokyo) |
| `singapore` | Singapore Exchange |
| `newzealand` | NZX |
| `brazil` | B3 (São Paulo) |

#### Example output

```
Top 3 stock(s) by volume on NYSE:

1. PCG - Pacific Gas & Electric Co. (NYSE)
   Volume: 114,326,369  |  Price: 16.60 USD  |  Change: -7.52%

2. NU - Nu Holdings Ltd. (NYSE)
   Volume: 79,125,113  |  Price: 14.30 USD  |  Change: -3.90%

3. PATH - UiPath, Inc. (NYSE)
   Volume: 53,108,174  |  Price: 18.15 USD  |  Change: -0.98%
```

With `--metric gainers` (or `losers`), the per-row stats lead with the percent change instead of volume, and the header reads `Top N gainers on <MARKET>:`:

```
Top 3 gainers on US:

1. PSQL - Pasqal Holding SA (NasdaqGM)
   Change: +95.20%  |  Price: 19.11 USD  |  Volume: 3,661,427

2. ESTC - Elastic N.V. (NYSE)
   Change: +19.31%  |  Price: 99.91 USD  |  Volume: 10,104,560

3. GAP - Gap, Inc. (The) (NYSE)
   Change: +12.94%  |  Price: 23.48 USD  |  Volume: 26,351,139
```

#### Tool usage (`--json`)

```bash
python3 market_top_volume.py --market us --metric losers --json --limit 2
```

```json
[
  {
    "rank": 1,
    "symbol": "SLS",
    "name": "SELLAS Life Sciences Group, Inc",
    "exchange": "NasdaqCM",
    "volume": 9814314,
    "price": 13.21,
    "change_percent": -13.15,
    "currency": "USD"
  },
  {
    "rank": 2,
    "symbol": "RBRK",
    "name": "Rubrik, Inc.",
    "exchange": "NYSE",
    "volume": 9407511,
    "price": 93.05,
    "change_percent": -13.05,
    "currency": "USD"
  }
]
```

The JSON array carries the same fields for every metric (`change_percent` is present for `volume` runs, `volume` is present for `gainers` / `losers` runs); only the ordering differs. On failure, an exit code of `1` is returned and a JSON object (`{"error": "..."}`) is printed to stderr instead of plain text.

### How it works

1. **Pick a data path from the market** — US markets (`us`, `nyse`, `nasdaq`, `amex`) use Yahoo's keyless predefined screeners (`query1.finance.yahoo.com/v1/finance/screener/predefined/saved`) — `most_actives`, `day_gainers`, or `day_losers` depending on `--metric` — each spanning the whole US market. Every other market uses the generic screener (`query1.finance.yahoo.com/v1/finance/screener`), which requires auth.
2. **Authenticate when needed** — For the generic screener, the script first hits `fc.yahoo.com` to pick up session cookies, then fetches a crumb token from `/v1/test/getcrumb`, and passes it on the screener call. The predefined path skips this.
3. **Query by the chosen metric** — The generic screener is POSTed with `quoteType: "EQUITY"`, a `region` equality filter (`gb`, `de`, `jp`, …), and a sort that depends on `--metric`: `dayvolume` DESC for `volume`, `percentchange` DESC for `gainers`, `percentchange` ASC for `losers`. For `gainers` / `losers` a `dayvolume > MIN_MOVER_VOLUME` operand is added server-side.
4. **Filter to the primary exchange** — Where a market maps to specific Yahoo exchange codes (e.g. `LSE`, `TOR`, `HKG`, or `NYQ` / `NMS,NCM,NGM` for the US sub-exchanges), quotes on other venues are dropped. `us` applies no exchange filter.
5. **Filter, sort, trim, display** — For `gainers` / `losers`, quotes below `MIN_MOVER_VOLUME` shares are dropped locally too (the server-side filter is unreliable for cross-listings). The survivors are re-sorted locally on the metric's field — `regularMarketVolume` descending, or `regularMarketChangePercent` descending (`gainers`) / ascending (`losers`) — trimmed to the top N, and printed as rank, ticker, company name, listing exchange, and the three stats (the metric's own stat first).

### Configuration

These are set as constants near the top of the file — edit them directly to change behavior:

| Constant | Default | Description |
|---|---|---|
| `MARKETS` | dict of ~28 aliases | Maps each `--market` value to its Yahoo `region` code, the set of listing-exchange codes to keep (or `None` for all), and whether to use the keyless `predefined` screener |
| `METRICS` | dict of 3 | Maps each `--metric` value to its predefined screener id, generic-screener sort field/direction, and local sort key |
| `DEFAULT_MARKET` | `"us"` | Market used when `--market` isn't passed |
| `DEFAULT_METRIC` | `"volume"` | Metric used when `--metric` isn't passed |
| `MIN_MOVER_VOLUME` | 50_000 | Minimum shares traded for a stock to appear in `gainers` / `losers` results |
| `DEFAULT_LIMIT` | 10 | Number of stocks to display |
| `REQUEST_TIMEOUT` | 15 | Per-request timeout in seconds |
| `HEADERS` | browser `User-Agent` | Required — Yahoo rejects requests without a browser-like User-Agent |

### API reference

- `fetch_predefined_quotes(session, scr_id)` — GETs a keyless predefined screener (`most_actives` / `day_gainers` / `day_losers`) and returns the raw list of quote dicts (US path).
- `fetch_region_quotes(session, region, sort_field, sort_type, min_volume=None)` — Performs the cookie + crumb handshake, POSTs the generic screener filtered to `region` (optionally with a `dayvolume` floor) and sorted as given, and returns the raw quote dicts.
- `get_movers(market, metric, limit)` — Chooses the data path from `MARKETS[market]` and the query shape from `METRICS[metric]`, applies the exchange-code filter (and, for movers, the `MIN_MOVER_VOLUME` floor), sorts locally on the metric's field, and returns the top N.
- `quote_to_dict(rank, quote)` — Flattens one quote into the `{rank, symbol, name, exchange, volume, price, change_percent, currency}` shape used for `--json`.
- `format_quote(row, metric)` — Formats one flattened row into a multi-line human-readable string, leading with the stat the metric ranks on.
- `parse_args(argv=None)` — Parses `--market`, `--metric`, `--limit`, and `--json` CLI flags.
- `main(argv=None)` — Entry point; fetches, handles network/parse errors, and prints results (human-readable or JSON).

### Error handling

- If any request fails (network error, timeout, non-2xx, missing crumb, or a screener error payload), the script prints an error and exits with status code 1 — plain text on stderr normally, or `{"error": "..."}` on stderr when `--json` is passed.
- An unrecognized `--market` or `--metric` value is rejected by argument parsing itself (exit code 2); the error message lists every valid choice.
- `--limit` values below 1 are clamped up to 1.
- If the screener returns no quotes for the market after filtering, the script prints `"No <metric> data returned for market '<MARKET>'."` (or `[]` with `--json`) and exits normally.

### Notes / limitations

- Relies on undocumented, unofficial Yahoo Finance endpoints — public and free, but with no guarantee they stay available or unchanged. The crumb/cookie handshake in particular is an implementation detail Yahoo can (and periodically does) alter.
- The non-US path depends on Yahoo populating `dayvolume` for the market's region; thinly covered markets may return few or stale rows.
- Exchange-code filters are best-effort. If Yahoo tags a listing with a code not in that market's set, a legitimate high-volume stock can be dropped; conversely `us` applies no filter at all, so an `amex`-style venue can appear under `--market us`.
- Volume and price are a live snapshot, delayed by Yahoo Finance's own reporting lag (typically ~15 minutes during market hours). Some markets quote price in minor units — e.g. LSE returns `GBp` (pence), not pounds.
- Company names come straight from Yahoo and are not normalized (casing, legal-entity suffixes, and depositary-receipt notes vary by market).
- `gainers` / `losers` are inherently small-cap-heavy even with the `MIN_MOVER_VOLUME` floor, and on non-US markets the region filter lets London-IOB and other cross-listings of foreign companies through (they carry an `LSE` exchange code but their own home currency). Treat the raw list as a starting point, not a curated one.

---

## stock_close_history.py

Prints the past daily open / high / low / close prices (plus adjusted close and volume) of one stock, using [Yahoo Finance](https://finance.yahoo.com/)'s public chart endpoint (`query1.finance.yahoo.com/v8/finance/chart/<symbol>`). No API key or authentication required.

### Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/)

```bash
pip install requests
```

### Usage

```bash
python3 stock_close_history.py SYMBOL [--range RANGE | --last N] [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--json]
```

| Flag | Default | Description |
|---|---|---|
| `SYMBOL` (positional) | — | Ticker in Yahoo notation: `AAPL`, `VOD.L`, `D05.SI`, `SAP.DE`, `RY.TO`, … |
| `--range RANGE` | `1mo` | Look-back window. One of `5d`, `1mo`, `3mo`, `6mo`, `ytd`, `1y`, `2y`, `5y`, `10y`, `max` |
| `--last N` | — | Return only the most recent `N` trading sessions (mutually exclusive with `--range`) |
| `--start` / `--end` | — | Explicit date window (`--end` defaults to today). Overrides `--range` / `--last` |
| `--json` | off | Print machine-readable JSON to stdout instead of a human-readable report — for calling this script as a tool from an agent or another program |

`--range`, `--last`, and `--start/--end` are three ways to pick the window; `--range` and `--last` are mutually exclusive at the argparse level, and `--start/--end` takes precedence over both.

#### Example output

```
AAPL - NasdaqGS (USD) - 5 session(s)

Date                Open        High         Low       Close         Volume
---------------------------------------------------------------------------
2026-08-21      312.0500    312.3800    307.0100    309.3500     46,876,800
2026-08-24      311.4700    313.3600    309.9700    310.3400     34,673,600
2026-08-25      310.7900    313.5900    308.2100    309.9000     25,869,800
2026-08-26      310.3000    315.4300    308.8000    313.4500     34,024,500
2026-08-27      310.5500    315.4000    309.4000    314.5800     32,419,200

Most recent session (2026-08-27): O 310.5500  H 315.4000  L 309.4000  C 314.5800 USD
```

An `Adj Close` column is added automatically when any adjusted close in the range differs from the raw close (i.e. a dividend or split fell inside the window).

#### Tool usage (`--json`)

```bash
python3 stock_close_history.py VOD.L --last 3 --json
```

```json
{
  "symbol": "VOD.L",
  "exchange": "LSE",
  "currency": "GBp",
  "prices": [
    { "date": "2026-08-26", "open": 117.8, "high": 118.2, "low": 117.075, "close": 117.9, "adj_close": 117.9, "volume": 29045061 },
    { "date": "2026-08-27", "open": 117.9, "high": 117.9, "low": 115.55, "close": 117.1, "adj_close": 117.1, "volume": 47994529 },
    { "date": "2026-08-28", "open": 117.9, "high": 118.486, "low": 116.846, "close": 118.45, "adj_close": 118.45, "volume": 64070460 }
  ]
}
```

With `--json`, results print as a JSON object on stdout. On failure, an exit code of `1` is returned and a JSON object (`{"error": "..."}`) is printed to stderr instead of plain text.

### How it works

Steps 1–2 (window building and fetching) plus the raw-payload navigation in step 3 live in [`yahoo_finance.py`](#yahoo_financepy), shared with `stock_candlestick.py`. This script keeps its own row shaping and output.

1. **Build the query window** — `yahoo_finance.build_params()` turns the args into params: `--start/--end` become `period1`/`period2` epoch bounds (the end is padded a day so the final session is inclusive); `--last N` fetches a generous calendar window (`N*2 + 10` days) to be trimmed later; otherwise `range` is passed through. `interval=1d` and `includeAdjustedClose=true` are always set.
2. **Fetch** — `yahoo_finance.fetch_history()` GETs the v8 chart endpoint for the symbol. A bad ticker comes back as a JSON error body (`{"chart": {"error": {...}}}`), which is raised as an error rather than parsed.
3. **Extract settled sessions** — `yahoo_finance.extract_series()` pulls `timestamp`, `indicators.quote[0]`'s `open` / `high` / `low` / `close` / `volume`, `indicators.adjclose[0].adjclose`, and the resolved `gmtoffset` into parallel lists; `extract_rows()` here zips them into row dicts. Rows whose `close` is `null` (an in-progress session or a data gap) are skipped, so only settled sessions are reported; any other field may still be `null` individually. Each timestamp is shifted by `meta.gmtoffset` before taking the calendar date, so dates match the exchange's local trading day.
4. **Trim and display** — For `--last N`, keeps the final `N` rows. Prints a table of date / open / high / low / close / (adj close if it differs) / volume, then a one-line "Most recent session" OHLC summary. `--json` emits `{symbol, exchange, currency, prices[]}` instead.

### Configuration

`DEFAULT_RANGE` is a constant at the top of this file; the shared fetch constants (`VALID_RANGES`, `REQUEST_TIMEOUT`, `HEADERS`) live in [`yahoo_finance.py`](#yahoo_financepy). Edit them directly to change behavior:

| Constant | Where | Default | Description |
|---|---|---|---|
| `DEFAULT_RANGE` | this file | `"1mo"` | Window used when no `--range`, `--last`, or `--start` is given |
| `VALID_RANGES` | `yahoo_finance.py` | `["5d", "1mo", …, "max"]` | Accepted `--range` keywords (Yahoo's own range vocabulary) |
| `REQUEST_TIMEOUT` | `yahoo_finance.py` | 15 | Request timeout in seconds |
| `HEADERS` | `yahoo_finance.py` | browser `User-Agent` | Required — Yahoo rejects requests without a browser-like User-Agent |

### API reference

- `extract_rows(result)` — Returns `(meta, rows)` where `rows` is the list of `{date, open, high, low, close, adj_close, volume}` dicts for settled sessions only. Calls `yahoo_finance.extract_series()` for the raw arrays, then rounds to 4 dp and formats `date` as a `YYYY-MM-DD` string.
- `parse_args(argv=None)` — Parses the positional `symbol` plus `--range` / `--last` (mutually exclusive), `--start`, `--end`, and `--json`.
- `main(argv=None)` — Entry point; calls `yahoo_finance.build_params()` / `yahoo_finance.fetch_history()`, extracts rows, trims for `--last`, and prints the report (human-readable or JSON).

See [`yahoo_finance.py`](#yahoo_financepy) for `build_params()` and `fetch_history()`.

### Error handling

- If the request fails (network error, timeout, non-2xx) or Yahoo returns an error body (`"No data found, symbol may be delisted"` for an unknown ticker), the script prints an error and exits with status code 1 — plain text on stderr normally, or `{"error": "..."}` on stderr when `--json` is passed.
- An invalid `--range` value is rejected by argument parsing (exit code 2); passing both `--range` and `--last` is likewise rejected.
- A malformed `--start` / `--end` date, `--end` without `--start`, or an end that isn't after the start exits with status code 1 and an explanatory message.
- A `--last` value below 1 exits with status code 1.
- If no settled sessions fall in the window, the script prints `"No settled price data found for <SYMBOL>."` (or `{"prices": []}` with `--json`) and exits normally.

### Notes / limitations

- Relies on an undocumented, unofficial Yahoo Finance endpoint — public and free, but with no guarantee it stays available or unchanged.
- The ticker must be in Yahoo's notation, including the exchange suffix for non-US listings (`.L`, `.SI`, `.DE`, `.PA`, `.TO`, `.AX`, `.NS`, `.HK`, `.T`, …). The script does not resolve company names to tickers.
- `open` is the first trade of the session, `high` / `low` the intraday extremes, `close` the raw session close; `adj_close` is `close` back-adjusted for splits and dividends and is the right field for comparing prices across a long span (only `close` is adjusted — `open` / `high` / `low` are as-traded).
- Prices are end-of-day snapshots in the listing currency, and some markets quote in minor units — e.g. LSE returns `GBp` (pence), not pounds.
- Date bucketing uses `meta.gmtoffset`; for exchanges Yahoo reports with an unusual offset the calendar date could in principle be off by a day near midnight boundaries.

---

## stock_candlestick.py

Fetches the past price history of one stock from [Yahoo Finance](https://finance.yahoo.com/)'s public chart endpoint (`query1.finance.yahoo.com/v8/finance/chart/<symbol>`) — sharing the fetch layer ([`yahoo_finance.py`](#yahoo_financepy)) with [`stock_close_history.py`](#stock_close_historypy) — and renders it as a candlestick (OHLC) chart with [matplotlib](https://matplotlib.org/), with simple moving averages of the close overlaid as lines (5 / 10 / 20 / 50 bars by default; via [`indicators.py`](#indicatorspy)). No API key or authentication required. The chart is written to a PNG by default, or shown in an interactive window with `--show`.

### Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/)
- [`matplotlib`](https://pypi.org/project/matplotlib/)
- the repo's own `yahoo_finance.py` and `indicators.py` modules (no install — run from the repo root so they import)

```bash
pip install requests matplotlib
```

### Usage

```bash
python3 stock_candlestick.py SYMBOL [--range RANGE | --last N] [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--interval {1d,1wk,1mo}] [--volume] [--ma N,N,...] [-o OUTPUT] [--show]
```

| Flag | Default | Description |
|---|---|---|
| `SYMBOL` (positional) | — | Ticker in Yahoo notation: `AAPL`, `VOD.L`, `D05.SI`, `SAP.DE`, `RY.TO`, … |
| `--range RANGE` | `6mo` | Look-back window. One of `5d`, `1mo`, `3mo`, `6mo`, `ytd`, `1y`, `2y`, `5y`, `10y`, `max` |
| `--last N` | — | Plot only the most recent `N` bars (mutually exclusive with `--range`) |
| `--start` / `--end` | — | Explicit date window (`--end` defaults to today). Overrides `--range` / `--last` |
| `--interval` | `1d` | Bar size: `1d` (daily), `1wk` (weekly), `1mo` (monthly) |
| `--volume` | off | Add a volume panel beneath the price panel |
| `--ma N,N,...` | `5,10,20,50` | Comma-separated simple-moving-average windows to overlay as lines. Pass `none` (or `""`) to disable; values are de-duplicated and sorted. Each average is in the bar unit selected by `--interval` |
| `-o` / `--output` | `<SYMBOL>_candlestick.png` | PNG path to write (`.` in the ticker becomes `_`) |
| `--show` | off | Open an interactive matplotlib window instead of writing a file |

`--range`, `--last`, and `--start/--end` are three ways to pick the window; `--range` and `--last` are mutually exclusive at the argparse level, and `--start/--end` takes precedence over both. There is no `--json` mode — the output is an image.

#### Example

```bash
python3 stock_candlestick.py NVDA --range 1y --volume --ma 20,50,200
```

```
Wrote NVDA_candlestick.png
```

The chart draws one candle per bar: a thin wick from the session low to high, and an open-to-close body. Direction is encoded **both** by hue and by fill so it survives greyscale and red/green colour-vision deficiency — up bars (close ≥ open) are hollow with a green edge, down bars (close < open) are filled red. A doji (open == close) collapses to a short horizontal line. Each `--ma` window is drawn as a coloured line over the candles (colours from `COLOR_MA`, cycled if there are more windows than colours), starting only once it has enough bars behind it. The title carries the ticker, exchange, bar count, interval, and date span; the legend maps the two candle styles and every moving-average line.

### How it works

Steps 1–2 (window building and fetching) plus the raw-payload navigation in step 3 live in [`yahoo_finance.py`](#yahoo_financepy), shared with `stock_close_history.py`. This script keeps its own bar shaping and the whole render stage.

1. **Build the query window** — `yahoo_finance.build_params(interval=…)`: `--start/--end` become `period1`/`period2` epoch bounds (end padded a day so the final bar is inclusive); `--last N` fetches a generous calendar window sized to the interval (`N*2 + 10` days for daily, wider for weekly/monthly) to be trimmed later; otherwise `range` is passed through. `interval` is whatever `--interval` selects.
2. **Fetch** — `yahoo_finance.fetch_history()` GETs the v8 chart endpoint for the symbol. A bad ticker comes back as a JSON error body (`{"chart": {"error": {...}}}`), which is raised rather than parsed.
3. **Extract bars** — `yahoo_finance.extract_series()` pulls `timestamp`, `indicators.quote[0]`'s `open` / `high` / `low` / `close` / `volume`, and `gmtoffset` into parallel lists; `extract_rows()` here zips them into row dicts. Any bar missing an OHLC value (an in-progress or gapped period) is skipped. Each timestamp is shifted by `meta.gmtoffset` before taking the date (kept as a `datetime`).
4. **Moving averages** — `indicators.moving_average()` computes each `--ma` window over the close of the **full** fetched series; for `--last N` the average lists are then sliced with the same `[-N:]` as the bars, so a window still shows correct values at the chart's left edge whenever the padded fetch reached back far enough. A window longer than the bars available plots nothing.
5. **Render** — With `--last N`, keeps the final `N` bars. Plots candles against an integer x-index (so weekends and holidays leave no gaps), draws each moving-average line where it is defined, relabels ~10 x-ticks with the bar dates, optionally adds a volume panel coloured to match each candle, and either writes the figure to the `-o` path (150 dpi) or shows it interactively.

### Configuration

The interval/range/colour constants at the top of this file are local; the shared fetch constants (`VALID_RANGES`, `REQUEST_TIMEOUT`, `HEADERS`) live in [`yahoo_finance.py`](#yahoo_financepy). Edit them directly to change behavior:

| Constant | Where | Default | Description |
|---|---|---|---|
| `VALID_INTERVALS` | this file | `["1d", "1wk", "1mo"]` | Accepted `--interval` values |
| `DEFAULT_RANGE` | this file | `"6mo"` | Window used when no `--range`, `--last`, or `--start` is given |
| `DEFAULT_INTERVAL` | this file | `"1d"` | Bar size used when `--interval` isn't passed |
| `DEFAULT_MA` | this file | `"5,10,20,50"` | Moving-average windows used when `--ma` isn't passed |
| `COLOR_UP` / `COLOR_DOWN` | this file | `#1a9850` / `#d73027` | Green edge for up bars, red fill for down bars |
| `COLOR_WICK` / `COLOR_GRID` / `COLOR_SURFACE` | this file | greys / white | Wick, gridline, and background colours |
| `COLOR_MA` | this file | 6 hues (blue, purple, gold, brown, pink, grey) | Moving-average line colours, assigned in window order and cycled if exhausted |
| `VALID_RANGES` | `yahoo_finance.py` | `["5d", "1mo", …, "max"]` | Accepted `--range` keywords (Yahoo's own range vocabulary) |
| `REQUEST_TIMEOUT` | `yahoo_finance.py` | 15 | Request timeout in seconds |
| `HEADERS` | `yahoo_finance.py` | browser `User-Agent` | Required — Yahoo rejects requests without a browser-like User-Agent |

### API reference

- `extract_rows(result)` — Returns `(meta, rows)` where `rows` is the list of `{date, open, high, low, close, volume}` dicts for complete bars only (`date` is a `datetime`). Calls `yahoo_finance.extract_series()` for the raw arrays.
- `_parse_ma_arg(value)` — argparse `type` for `--ma`: turns `"5,10,20,50"` into `[5, 10, 20, 50]` (de-duplicated, sorted); `""` / `"none"` / `"off"` give `[]`. Raises `argparse.ArgumentTypeError` on a non-integer or non-positive window.
- `render_chart(symbol, exchange, currency, interval, rows, ma_series, out_path, show, with_volume)` — Draws the candlestick figure, the moving-average lines from `ma_series` (a `{window: [value|None, …]}` dict aligned to `rows`), and the optional volume panel, then saves or shows it. Imports matplotlib lazily and selects the `Agg` backend unless `--show`.
- `parse_args(argv=None)` — Parses the positional `symbol` plus `--range` / `--last` (mutually exclusive), `--start`, `--end`, `--interval`, `--volume`, `--ma`, `--output`, and `--show`.
- `main(argv=None)` — Entry point; calls `yahoo_finance.build_params()` / `yahoo_finance.fetch_history()`, extracts rows, computes the `--ma` averages via `indicators.moving_average()`, trims both for `--last`, resolves the output path, and renders.

See [`yahoo_finance.py`](#yahoo_financepy) for `build_params()` and `fetch_history()`.

### Error handling

- If the request fails (network error, timeout, non-2xx) or Yahoo returns an error body (`"No data found, symbol may be delisted"` for an unknown ticker), the script prints `Error: …` to stderr and exits with status code 1.
- An invalid `--range` or `--interval` value, or a `--ma` list that isn't comma-separated positive integers (or `none`), is rejected by argument parsing (exit code 2); passing both `--range` and `--last` is likewise rejected.
- A malformed `--start` / `--end` date, `--end` without `--start`, or an end that isn't after the start exits with status code 1 and an explanatory message.
- A `--last` value below 1 exits with status code 1.
- If no complete bars fall in the window, the script prints `Error: no price data found for '<SYMBOL>'` and exits with status code 1.
- If matplotlib isn't installed, it prints `Error: matplotlib is required (pip install matplotlib)` and exits with status code 1.

### Notes / limitations

- Relies on an undocumented, unofficial Yahoo Finance endpoint — public and free, but with no guarantee it stays available or unchanged.
- The ticker must be in Yahoo's notation, including the exchange suffix for non-US listings (`.L`, `.SI`, `.DE`, `.PA`, `.TO`, `.AX`, `.NS`, `.HK`, `.T`, …). The script does not resolve company names to tickers.
- Candle bodies and the moving averages use the **raw** open/high/low/close — prices are not split/dividend-adjusted, so a split inside the window shows up as a large gap.
- Moving averages are computed only from bars in the fetched window (plus the `--last` padding). A window near or above the number of bars available renders a short line or nothing at all — widen `--range` / `--last` to give a long average enough history.
- The figure width scales with the bar count (`~0.11 in` per bar), so a long daily range produces a very wide, short image — use `--interval 1wk` or `1mo` for multi-year spans.
- `--show` needs a working matplotlib GUI backend and a display; in a headless environment omit it and read the PNG.
- Prices are end-of-day snapshots in the listing currency, and some markets quote in minor units — e.g. LSE returns `GBp` (pence).

---

## yahoo_finance.py

Shared helper module for [`stock_close_history.py`](#stock_close_historypy) and [`stock_candlestick.py`](#stock_candlestickpy). It holds everything the two scripts had in common — the Yahoo Finance chart-endpoint constants, the query-window builder, the HTTP call, and the raw-payload navigation. Each script keeps its own row shaping (rounding, date type, which rows to drop) and its own output stage. Not a CLI — it is imported, not run.

### Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/)

### Constants

| Constant | Default | Description |
|---|---|---|
| `CHART_URL` | `…/v8/finance/chart/{symbol}` | Yahoo chart-endpoint URL template |
| `HEADERS` | browser `User-Agent` | Required — Yahoo rejects requests without a browser-like User-Agent |
| `REQUEST_TIMEOUT` | 15 | Request timeout in seconds |
| `VALID_RANGES` | `["5d", "1mo", …, "max"]` | Accepted `--range` keywords (Yahoo's own range vocabulary) |
| `SECONDS_PER_DAY` | 86400 | Used to pad an explicit `--end` by a day so the final bar is inclusive |

### API reference

- `parse_date(value)` — Parses a `YYYY-MM-DD` string to a UTC `datetime`, raising `ValueError` with a clear message on a bad format.
- `build_params(interval="1d", range_=None, start=None, end=None, last=None)` — Returns the chart-endpoint query params. The window is chosen by, in priority order: an explicit `start`/`end` pair (→ `period1`/`period2`, end padded a day), then `last` (→ a calendar look-back widened for `1wk` / `1mo` bars), then `range_`. Raises `ValueError` for `end` without `start` or an `end` not after `start`. `includeAdjustedClose=true` is always set. Callers pass `interval="1d"` (the default) for daily data.
- `fetch_history(symbol, params)` — GETs the v8 chart endpoint, raises `requests.RequestException` on a Yahoo error body or an empty result, and returns the first `chart.result` object.
- `extract_series(result)` — Returns `(meta, series)` where `series` is a dict of parallel lists straight off the payload — `timestamp`, `open`, `high`, `low`, `close`, `volume` — plus `adjclose` (a list or `None`) and the resolved `gmtoffset`. Callers turn these into row dicts.

### Notes / limitations

- Changing a constant or the `build_params` window logic here affects **both** `stock_*` scripts. Behaviour was kept identical to the pre-refactor scripts: the interval-aware `--last` look-back is a no-op for the default `interval="1d"`, so `stock_close_history.py` gets the same params it did before.

---

## indicators.py

Small, dependency-free technical indicators over a price series — a plain list of numbers, oldest session first, such as the `close` field of each row from [`stock_close_history.py`](#stock_close_historypy)'s `--json` output. Not a CLI: it is imported, not run. Used by [`stock_candlestick.py`](#stock_candlestickpy) (moving-average overlays) and the [`stock-trend`](#claude-code-agent-stock-trend) agent.

### Requirements

- Python 3.7+ (standard library only)

### API reference

- `moving_average(prices, n)` — Simple moving average over an `n`-session window. Returns a list the **same length** as `prices`: element `i` is the mean of `prices[i-n+1 .. i]`, or `None` for the first `n-1` positions where a full window isn't available yet, so the result lines up session-for-session with the source rows. Raises `ValueError` if `n < 1`.
- `price_vs_moving_average(prices, n)` — Where each session's price sits relative to its `n`-session SMA. Returns a list the **same length** as `prices`: `"above"`, `"below"`, or `"equal"` for each session where the SMA is defined, and `None` for the first `n-1` positions where it isn't yet. Take `[-1]` for the current reading. Raises `ValueError` (via `moving_average`) if `n < 1`.
- `moving_average_cross(prices, fast, slow)` — Where the `fast`-session SMA sits relative to the `slow`-session SMA. Returns a list the **same length** as `prices`: `"above"`, `"below"`, or `"equal"` for each session where **both** averages are defined (from index `max(fast, slow) - 1` on), else `None`. Take `[-1]` for the current reading; a change in the value is a crossover (the golden / death cross for e.g. `fast=50, slow=200`). Raises `ValueError` (via `moving_average`) if either window `< 1`.
- `trend(prices, window=None, flat_threshold=0.01)` — Classifies the series as `"up"`, `"down"`, or `"flat"`. Fits a least-squares line through the closes and measures the move that line implies from its first fitted point to its last, as a fraction of the mean price; if that fitted move is smaller than `flat_threshold` (default `0.01` = 1%) in magnitude the series is `"flat"` (direction is just noise), otherwise its sign decides up vs down. `window=N` restricts the fit to the last `N` prices. Raises `ValueError` on fewer than 2 prices (or `window < 2`).
- `_ols_slope(values)` — Internal: least-squares slope of `values` against `x = 0, 1, 2, …` (per step).

### Examples

```python
>>> from indicators import (
...     moving_average, price_vs_moving_average, moving_average_cross, trend)
>>> moving_average([1, 2, 3, 4, 5], 3)
[None, None, 2.0, 3.0, 4.0]
>>> price_vs_moving_average([10, 10, 10, 7, 13], 3)
[None, None, 'equal', 'below', 'above']
>>> moving_average_cross([1, 2, 3, 4, 5, 6], 2, 4)
[None, None, None, 'above', 'above', 'above']
>>> trend([1, 2, 3, 4, 5])
'up'
>>> trend([5, 4, 3, 2, 1])
'down'
>>> trend([10, 10, 10, 10])
'flat'
```

Pull real closes straight from the JSON tool:

```python
import json, subprocess
from indicators import (
    trend, moving_average, price_vs_moving_average, moving_average_cross)

out = subprocess.run(
    ["python3", "stock_close_history.py", "AAPL", "--range", "6mo", "--json"],
    capture_output=True, text=True, check=True,
).stdout
closes = [r["close"] for r in json.loads(out)["prices"]]

trend(closes)                 # -> "up" / "down" / "flat" over the whole span
trend(closes, window=20)      # -> the near-term (last 20 sessions) trend
moving_average(closes, 50)[-1]              # -> current 50-session SMA
price_vs_moving_average(closes, 50)[-1]     # -> "above" / "below" / "equal"
moving_average_cross(closes, 20, 50)[-1]   # -> is the 20-SMA above the 50-SMA?
```

### Notes / limitations

- `moving_average` re-sums each window, so it is O(len·n) — fine for stock series (hundreds–thousands of points). For very long inputs keep a running sum instead (O(len)), accepting minor floating-point drift. `price_vs_moving_average` and `moving_average_cross` build on it and inherit that cost.
- `trend` is a mechanical read of past closing prices — a straight-line fit, nothing more. It is not a forecast, and `flat_threshold` is a blunt single knob: tune it up to ignore weaker trends, down to be more sensitive. It does not scale with the series' own volatility.
- All of these take raw `close` values. Pass `adj_close` instead when spanning a split or large dividend.

---

## stock_tech_buzz_agent.py

An agent script that combines [`market_top_volume.py`](#market_top_volumepy) and [`hottest_tech_discussions.py`](#hottest_tech_discussionspy): it pulls the top 10 highest-volume stocks on **both** NYSE and Nasdaq (20 stocks total), pulls the ~40 hottest tech discussions from Hacker News (the `--discussion-limit` default is 50 but the underlying script ranks only its first 40 candidates), and reports which of those stocks are actually being talked about — pairing each matched stock with the discussion(s) that mention it. No API key or authentication required.

Requires `market_top_volume.py` and `hottest_tech_discussions.py` to be present in the same directory — it imports them directly rather than shelling out.

### Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/)

```bash
pip install requests
```

### Usage

```bash
python3 stock_tech_buzz_agent.py [--stock-limit N] [--discussion-limit N] [--json]
```

| Flag | Default | Description |
|---|---|---|
| `--stock-limit N` | 10 | Number of top-volume stocks to pull *per exchange* (so total candidates = 2×N) |
| `--discussion-limit N` | 50 | Number of hottest tech discussions to search. Capped by `hottest_tech_discussions.py`'s candidate pool (`CANDIDATE_POOL_SIZE`, 40) — values above ~40 return at most ~40 |
| `--json` | off | Print machine-readable JSON to stdout instead of a human-readable report — for calling this script as a tool from an agent or another program |

#### Example output

```
Fetching top 10 NYSE + top 10 Nasdaq stocks by volume, and searching the top 50 tech discussions...

1. NVDA - NVIDIA Corporation (NASDAQ, Volume: 92,250,395)
   - "NVIDIA unveils new AI chip" (Score: 512)
     https://news.ycombinator.com/item?id=12345678

...
```

If no top-volume stock is mentioned in any of the fetched discussions (the common case — ticker mentions in HN titles are relatively rare), it prints:

```
No overlap found between the top 20 volume stocks and the top 39 tech discussions.
```

(The discussion count in that message is usually lower than `--discussion-limit`: the underlying [`hottest_tech_discussions.py`](#hottest_tech_discussionspy) only ranks its first `CANDIDATE_POOL_SIZE` (40) top stories, so a default `--discussion-limit 50` yields ~40 at most, and a few more can drop out if their detail fetch fails.)

#### Tool usage (`--json`)

```bash
python3 stock_tech_buzz_agent.py --json
```

```json
[
  {
    "symbol": "NVDA",
    "name": "NVIDIA Corporation",
    "exchange": "NASDAQ",
    "volume": 92250395,
    "price": 216.85,
    "change_percent": -0.32635,
    "discussions": [
      {
        "title": "NVIDIA unveils new AI chip",
        "score": 512,
        "comments": 234,
        "discussion_url": "https://news.ycombinator.com/item?id=12345678"
      }
    ]
  }
]
```

With `--json`, the leading progress line is suppressed and results print as a JSON array (empty `[]` if no stock was mentioned) on stdout. On failure, an exit code of `1` is returned and a JSON object (`{"error": "..."}`) is printed to stderr instead of plain text.

### How it works

1. **Fetch top-volume stocks** — Calls `market_top_volume.get_movers()` with metric `"volume"` once for `"nyse"` and once for `"nasdaq"` (each with `--stock-limit`), tagging each quote with its source exchange and de-duplicating by symbol.
2. **Fetch tech discussions** — Calls `hottest_tech_discussions.get_hottest_tech_discussions()` with `--discussion-limit`. That function only inspects the first `CANDIDATE_POOL_SIZE` (40) of HN's current top stories, so a `--discussion-limit` above ~40 effectively tops out there.
3. **Match stocks to discussions** — For every stock, checks every discussion's title for either: (a) the ticker symbol as a case-sensitive whole word (e.g. `NVDA`), or (b) the company name — with legal-entity suffixes like "Corporation"/"Inc."/"Ltd." stripped — as a case-insensitive whole-word/phrase match (e.g. "NVIDIA Corporation" → "NVIDIA").
4. **Filter and report** — Keeps only stocks with at least one matching discussion, and prints each stock paired with the discussion(s) that mentioned it.

### Configuration

These are set as constants near the top of the file — edit them directly to change behavior:

| Constant | Default | Description |
|---|---|---|
| `STOCK_LIMIT_PER_EXCHANGE` | 10 | Stocks pulled per exchange before matching |
| `DISCUSSION_LIMIT` | 50 | Discussions searched for mentions |
| `EXCHANGES` | `("nyse", "nasdaq")` | Exchanges queried via `market_top_volume.get_movers()` |
| `AMBIGUOUS_SYMBOLS` | e.g. `{"AI", "ON", "IT", "ALL", ...}` | Ticker symbols excluded from symbol-matching because they double as common English words/acronyms (company-name matching still applies to these) |
| `NAME_SUFFIXES` | regex of legal-entity suffixes | Suffixes stripped from company names before matching (e.g. "Corporation", "Inc.", "Ltd.") |

### API reference

- `get_top_volume_stocks(limit_per_exchange=10)` — Fetches and combines top-volume quotes from both exchanges, de-duplicated by symbol.
- `normalize_company_name(name)` — Strips a trailing legal-entity suffix from a company name.
- `stock_mentions_in_title(quote, title)` — Returns `True` if a quote's ticker symbol or normalized company name appears in a discussion title.
- `find_stock_buzz(limit_per_exchange=10, discussion_limit=50)` — Orchestrates fetching both data sources and matching; returns `(results, stocks, discussions)`.
- `result_to_dict(result)` — Flattens one `{stock, discussions}` match into the record used for **both** output modes (nested discussion URLs come from `hottest_tech_discussions.discussion_url`).
- `format_result(rank, row)` — Renders a `result_to_dict()` record as a text block.
- `parse_args(argv=None)` — Parses `--stock-limit`, `--discussion-limit`, and `--json` CLI flags.
- `main(argv=None)` — Entry point; fetches, handles top-level network errors, and prints results.

### Error handling

- If fetching either the stock data or the discussion data fails (network error, timeout, non-2xx response), the script prints an error and exits with status code 1 — plain text on stderr normally, or a JSON object (`{"error": "..."}`) on stderr when `--json` is passed.
- If no stock is mentioned in any discussion, the script prints a "No overlap found..." message (or `[]` with `--json`) and exits normally — this is expected and common, not an error condition.

### Notes / limitations

- Matching is title-only — it does not inspect discussion body text, comments, or the linked article itself, so mentions buried in the article or comment thread are missed.
- Ticker-symbol matching is case-sensitive and whole-word to cut down on false positives, but is inherently heuristic: an all-caps acronym coincidentally matching a real ticker (outside the curated `AMBIGUOUS_SYMBOLS` list) could still produce a false positive, and a legitimate mention using unusual casing could be missed.
- Company-name matching only strips one legal-entity suffix; a distinctive-enough remaining name (e.g. "NVIDIA", "Moderna") is a solid signal, but this hasn't been tuned against every possible company name shape.
- Inherits the limitations of both underlying scripts — see [`market_top_volume.py`](#market_top_volumepy) and [`hottest_tech_discussions.py`](#hottest_tech_discussionspy)'s own Notes / limitations sections.

---

## Claude Code agent: `hottest-tech-discussions`

A [Claude Code](https://claude.com/claude-code) subagent definition at `.claude/agents/hottest-tech-discussions.md`. It doesn't call any external API itself — it shells out to [`hottest_tech_discussions.py`](#hottest_tech_discussionspy) via the `Bash` tool and reports the results conversationally.

### Purpose

Lets Claude Code answer questions like "what's trending in tech today?" or "top HN discussions" by running the script and summarizing its JSON output, instead of guessing or using stale training data.

### How it's invoked

- **Automatically** — Claude Code selects this subagent on its own for tech-news/trends questions, based on the `description` field in its frontmatter.
- **Explicitly** — via the `Agent` tool with `subagent_type: "hottest-tech-discussions"`.

Subagent definitions are loaded when a Claude Code session starts, so a newly added or edited agent file only takes effect in sessions started afterward — not the session it was created in.

### What it does

1. Runs `python3 hottest_tech_discussions.py --json --limit N` (default `N=10`, or whatever count the user asked for) from the repo root.
2. Parses the JSON array of stories.
3. Reports them as a concise list — title, score, comment count, and links — without fabricating data. If the command fails, it surfaces the `{"error": "..."}` from stderr instead of retrying repeatedly or inventing results.

### Configuration

The agent's frontmatter restricts it to the `Bash` tool only, since running the script and reading its stdout is all it needs.

| Field | Value |
|---|---|
| `tools` | `Bash` |
| Underlying script | [`hottest_tech_discussions.py`](#hottest_tech_discussionspy) |

### Notes / limitations

- Requires `hottest_tech_discussions.py` (and its `requests` dependency) to be present and runnable from the repo root.
- Inherits all the limitations of [`hottest_tech_discussions.py`](#hottest_tech_discussionspy) itself (score-based "hottest" definition, no tech-specific keyword filtering, live-snapshot results).

---

## Claude Code agent: `top-volume-stock`

A [Claude Code](https://claude.com/claude-code) subagent definition at `.claude/agents/top-volume-stock.md`. Like the `hottest-tech-discussions` agent, it calls no API itself — it shells out to [`market_top_volume.py`](#market_top_volumepy) via the `Bash` tool and reports the result conversationally.

### Purpose

Lets Claude Code answer questions like "what's the top volume stock on the NYSE?", "biggest gainers on NASDAQ today", "worst-performing stocks on the LSE", or "most active stock in Singapore" by running the script and summarizing its JSON output, instead of guessing or using stale training data.

### How it's invoked

- **Automatically** — Claude Code selects this subagent on its own for "which stocks are trading the most / up the most / down the most on \<market\>" questions, based on the `description` field in its frontmatter.
- **Explicitly** — via the `Agent` tool with `subagent_type: "top-volume-stock"`.

Subagent definitions are loaded when a Claude Code session starts, so a newly added or edited agent file only takes effect in sessions started afterward — not the session it was created in.

### What it does

1. Maps the user's phrasing to a `--market` value (e.g. "London" → `uk`, "Frankfurt" / "DAX" → `germany`, "Toronto" → `canada`, "Bombay" → `bse`), defaulting to `us` when no market is named.
2. Maps the user's intent to a `--metric` value — `volume` for "most active" / "highest volume" (the default), `gainers` for "top gainers" / "biggest risers", `losers` for "top losers" / "biggest fallers".
3. Runs `python3 market_top_volume.py --market MARKET --metric METRIC --limit N --json` from the repo root (`--limit 1` when the user wants only the single leader).
4. Parses the JSON array (already ordered by the chosen metric) and leads with the rank-1 stock — symbol, company name, and the stats with the metric's own figure first — then lists any further rows requested. If the command fails, it surfaces the `{"error": "..."}` from stderr and retries at most once. It notes when a market has no matching `--market` choice rather than guessing.

### Configuration

The agent's frontmatter restricts it to the `Bash` tool only, since running the script and reading its stdout is all it needs.

| Field | Value |
|---|---|
| `tools` | `Bash` |
| Underlying script | [`market_top_volume.py`](#market_top_volumepy) |

### Notes / limitations

- Requires `market_top_volume.py` (and its `requests` dependency) to be present and runnable from the repo root.
- Inherits all the limitations of [`market_top_volume.py`](#market_top_volumepy) itself (unofficial Yahoo endpoints, best-effort exchange filtering, live-snapshot figures, minor-unit prices on some markets, small-cap-heavy and cross-listing-prone `gainers` / `losers` lists).

---

## Claude Code agent: `stock-closing-price`

A [Claude Code](https://claude.com/claude-code) subagent definition at `.claude/agents/stock-closing-price.md`. Like the other agents here, it calls no API itself — it shells out to [`stock_close_history.py`](#stock_close_historypy) via the `Bash` tool and reports the result conversationally.

### Purpose

Lets Claude Code answer questions like "what did AAPL close at yesterday?", "Tesla's OHLC last week", or "DBS high and low for August" by running the script and summarizing its JSON output, instead of guessing or using stale training data. Despite the name, it reports the full daily open / high / low / close, not just the close.

### How it's invoked

- **Automatically** — Claude Code selects this subagent on its own for "past / previous / historical open, high, low, or closing price of \<company\>" questions, based on the `description` field in its frontmatter.
- **Explicitly** — via the `Agent` tool with `subagent_type: "stock-closing-price"`.

Subagent definitions are loaded when a Claude Code session starts, so a newly added or edited agent file only takes effect in sessions started afterward — not the session it was created in.

### What it does

1. Resolves the company to a Yahoo ticker, adding the exchange suffix for non-US listings (`.L`, `.SI`, `.DE`, …); if the ticker is uncertain it says so rather than guessing.
2. Chooses the window from the user's phrasing — `--last 2` for "yesterday" / "last session", `--last N` for "past N days", `--start`/`--end` for a named month or span, `--range ytd|1y|5y|…` for a longer horizon, otherwise the default `--range 1mo`.
3. Runs `python3 stock_close_history.py SYMBOL <window flags> --json` from the repo root, parses the `{symbol, exchange, currency, prices[]}` object (each price row carrying `open`, `high`, `low`, `close`, `adj_close`, `volume`), and leads with the figure the user asked for — the most recent close by default, or the full OHLC when they asked for open / high / low / a range — followed by a compact table if a series was requested. On failure it surfaces the `{"error": "..."}` from stderr and retries at most once.

### Configuration

The agent's frontmatter restricts it to the `Bash` tool only, since running the script and reading its stdout is all it needs.

| Field | Value |
|---|---|
| `tools` | `Bash` |
| Underlying script | [`stock_close_history.py`](#stock_close_historypy) |

### Notes / limitations

- Requires `stock_close_history.py` and its `yahoo_finance.py` helper module (plus the `requests` dependency) to be present and runnable from the repo root.
- Only as good as the ticker it picks — a wrong or ambiguous symbol yields the wrong company's prices or a "symbol may be delisted" error.
- Inherits all the limitations of [`stock_close_history.py`](#stock_close_historypy) itself (unofficial Yahoo endpoint, Yahoo-notation tickers only, end-of-day snapshots, minor-unit prices on some markets).

---

## Claude Code agent: `stock-candlestick-chart`

A [Claude Code](https://claude.com/claude-code) subagent definition at `.claude/agents/stock-candlestick-chart.md`. Like the other agents here, it calls no API itself — it shells out to [`stock_candlestick.py`](#stock_candlestickpy) via the `Bash` tool, then `Read`s the generated PNG to confirm it rendered.

### Purpose

Lets Claude Code answer requests like "show me a candlestick chart of AAPL", "chart Tesla's last 3 months", "plot DBS weekly candles for the first half of the year", or "candlestick chart for Vodafone since June with volume" by running the script and handing back the chart, instead of describing prices from stale training data.

### How it's invoked

- **Automatically** — Claude Code selects this subagent on its own for "see / plot / draw / visualize \<company\>'s price history as a chart" requests, based on the `description` field in its frontmatter.
- **Explicitly** — via the `Agent` tool with `subagent_type: "stock-candlestick-chart"`.

Subagent definitions are loaded when a Claude Code session starts, so a newly added or edited agent file only takes effect in sessions started afterward — not the session it was created in.

### What it does

1. Resolves the company to a Yahoo ticker, adding the exchange suffix for non-US listings (`.L`, `.SI`, `.DE`, …); if the ticker is uncertain it says so rather than guessing.
2. Chooses the window from the user's phrasing — `--last N` or a `--range` keyword for "recent" / "past N months" / "this year", `--start`/`--end` for a named month or span, otherwise the script default of `--range 6mo`. Adds `--interval 1wk` / `1mo` for long horizons or when weekly/monthly candles are asked for, `--volume` when volume is mentioned, and `--ma` only when the user asks for specific moving averages (the script overlays `5,10,20,50` by default) or asks for none.
3. Runs `python3 stock_candlestick.py SYMBOL <window flags> [--interval …] [--volume] [--ma …] -o /tmp/<TICKER>_candlestick.png` from the repo root — always to an explicit temp path (never `--show`, never cluttering the repo).
4. Reads the PNG to verify it rendered, then reports a one- or two-sentence summary (ticker, exchange, period, interval, and a brief read of the trend) ending with the absolute path of the chart on its own line so the caller can display it. On failure it surfaces the error from stderr and retries at most once.

### Configuration

The agent's frontmatter restricts it to `Bash` (run the script) and `Read` (verify the PNG).

| Field | Value |
|---|---|
| `tools` | `Bash`, `Read` |
| Underlying script | [`stock_candlestick.py`](#stock_candlestickpy) |

### Notes / limitations

- Requires `stock_candlestick.py` and its `yahoo_finance.py` + `indicators.py` helper modules (plus the `requests` + `matplotlib` dependencies) to be present and runnable from the repo root.
- Only as good as the ticker it picks — a wrong or ambiguous symbol yields the wrong company's chart or a "symbol may be delisted" error.
- The subagent's own reply isn't shown to the user directly; it returns the PNG path for the calling session to display.
- Inherits all the limitations of [`stock_candlestick.py`](#stock_candlestickpy) itself (unofficial Yahoo endpoint, Yahoo-notation tickers only, raw unadjusted prices, wide images for long daily ranges).

---

## Claude Code agent: `stock-trend`

A [Claude Code](https://claude.com/claude-code) subagent definition at `.claude/agents/stock-trend.md`. Like the other agents here, it calls no API itself — it shells out via the `Bash` tool to [`stock_close_history.py`](#stock_close_historypy) for the price history and then to the [`indicators.py`](#indicatorspy) functions (`trend`, `moving_average`) to classify it.

### Purpose

Lets Claude Code answer requests like "is AAPL trending up?", "what's the trend on Tesla?", "is Vodafone in a downtrend?", "has DBS been going up or down lately?", or "is NVDA on an uptrend this quarter?" with a mechanical read of recent closing prices, instead of guessing a direction from stale training data.

### How it's invoked

- **Automatically** — Claude Code selects this subagent on its own for questions about the direction, trend, or momentum of a named company or ticker over time, based on the `description` field in its frontmatter.
- **Explicitly** — via the `Agent` tool with `subagent_type: "stock-trend"`.

Subagent definitions are loaded when a Claude Code session starts, so a newly added or edited agent file only takes effect in sessions started afterward — not the session it was created in.

### What it does

1. Resolves the company to a Yahoo ticker, adding the exchange suffix for non-US listings (`.L`, `.SI`, `.DE`, …); if the ticker is uncertain it says so rather than guessing.
2. Chooses the window from the user's phrasing — `--range 3mo` for "lately" / "this quarter", `--range ytd` / `1y` for "this year" / "past year", `--last N` for "past N days/weeks", `--start`/`--end` for a named month or span, otherwise `--range 6mo`.
3. Runs `python3 stock_close_history.py SYMBOL <window flags> --json > /tmp/stock_trend.json` from the repo root, then a `python3` heredoc that imports `indicators` and prints the overall `trend()` verdict, the `trend()` over the last 20 and last 5 sessions, the percentage change across the span, and — via `price_vs_moving_average()` — whether the last close is above or below each of its 5 / 10 / 20 / 50-session moving averages.
4. Reports a one-line verdict (up trend / down trend / roughly flat over the dates examined) plus a few supporting lines, calling out when the short-window trend disagrees with the overall one, and closes with a caveat that this is not a prediction or investment advice. On failure it surfaces the `{"error": "..."}` from stderr and retries at most once.

### Configuration

The agent's frontmatter restricts it to `Bash` (run the script and the analysis snippet).

| Field | Value |
|---|---|
| `tools` | `Bash` |
| Underlying script | [`stock_close_history.py`](#stock_close_historypy) |
| Underlying module | [`indicators.py`](#indicatorspy) |

### Notes / limitations

- Requires `stock_close_history.py` (with its `yahoo_finance.py` helper and the `requests` dependency) and `indicators.py` to be present and runnable from the repo root — the analysis step must run with the repo root on `sys.path` so `import indicators` resolves.
- Only as good as the ticker it picks — a wrong or ambiguous symbol yields the wrong company's trend or a "symbol may be delisted" error.
- The verdict is a straight-line fit over past closes (see [`indicators.py`](#indicatorspy) limitations): a mechanical description, not a forecast, and sensitive to the window chosen and to `flat_threshold`.
- Inherits all the limitations of [`stock_close_history.py`](#stock_close_historypy) itself (unofficial Yahoo endpoint, Yahoo-notation tickers only, end-of-day snapshots, minor-unit prices on some markets).
