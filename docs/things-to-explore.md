# Things to explore

A backlog of data sources and features that could be added on top of the existing
scripts. The open `[ ]` items aren't implemented yet, and their API claims haven't
been verified; entries without a checkbox are kept as the record of a source check
(see OSV.dev under "Tech and news", and Lobsters). Check the endpoint, its terms, its robots.txt and whether it needs a
key before building on it (see the Lobsters note under "More discussion sources"
for why).

Ideas that reuse an existing shared module (`weather.py`, `yahoo_finance.py`,
`url_*.py`) are listed first in each section, because they need the least new code.

When one of these is implemented, follow the usual repo conventions: script + tests
+ agent + feature specs (`docs/features/script/...`, `docs/features/agent/...`) +
both READMEs in the same change. Then remove the item from this list.

## From the source audit

The [source audit](source-audit.md) of 2026-10-20 left one item open. It comes
before the top picks because it's about the repo's existing sources, not new ones.

- [ ] **Replace or remove Yahoo Finance.** Its API hosts' robots.txt says
  `Disallow: /` to every client, `finance.yahoo.com` blocks Claude agents by name,
  and its terms forbid automated data collection without permission. Everything in
  the stock section depends on it, so this needs a decision first: remove the stock
  tools, or move them to a licensed price-data source (which needs its own
  robots.txt-and-terms check before anything is built).

  **Replacement shortlist**, checked on 2026-10-20 against what the stock section
  uses: (A) daily prices for stocks on ~10 exchanges plus indices, FX, crypto and
  futures; (B) top movers for ~20 markets; (C) fundamentals; (D) earnings and
  dividend dates; (E) analyst targets, ratings and upgrades / downgrades;
  (F) holders and insider trades. Free tiers and coverage marked "?" were not
  confirmed.

  | Provider | Covers | Free tier | Terms and robots.txt |
  |---|---|---|---|
  | **Alpha Vantage** | A (global stocks, FX, crypto, a few commodities; adjusted closes and indices are paid; free daily stock history is only the latest 100 sessions), B (US only), C, D, E (target and rating counts only), F | 25 requests/day; unlimited for verified open-source or educational projects | Free use is "personal, non-commercial" for "investment analysis, research, testing, monitoring"; nothing on AI, and its docs promote use with LLMs and agents (official MCP server). No robots.txt |
  | **SEC EDGAR** (`data.sec.gov`) | C and F for US filers only (XBRL company facts, Form 4, 13F); no prices or estimates | No key; 10 requests/second | Free to "access and download"; declare a name and contact email in the User-Agent. `data.sec.gov` has no robots.txt; `sec.gov` disallows only search, admin and login paths |
  | **Finnhub** | C, D, E (recommendation trends); price history reportedly paid; rest ? | 60/minute; free endpoints unconfirmed | "Strictly for personal use"; no redistributing data "or derived results"; nothing on AI |
  | **Twelve Data** | A (US stocks, FX, crypto only); C–F paid | 800/day, 8/minute | No commercial use of free-tier data, no redistribution or external display, no caching beyond documented limits; nothing on AI. API host robots.txt is `Disallow: /`, but it's a documented keyed API, so its terms decide |
  | **EODHD** | A (global end of day); rest ? | 20 calls/day, 1 year of end-of-day history | Non-professional users may "store, manipulate, and analyze" but not redistribute or display; nothing on AI. `/api/` disallowed in robots.txt (same reasoning as Twelve Data) |
  | **Tiingo** | A (US and Chinese stocks, ETFs, funds, crypto; FX not on its pricing page); fundamentals paid | 1,000/day, 50/hour, 500 symbols/month | Terms page not read (404). Its pricing page licenses every individual plan for "internal use only": your own use, without displaying or sharing the data with anyone. api.tiingo.com redirects to tiingo.com, whose robots.txt disallows only `/admin` |
  | **FMP** | C–F claimed; ? | ? | Terms not read (403 to automated fetches); display or redistribution needs a separate licence |
  | **Massive** (formerly Polygon) | US only | ? | Only the terms index was read |
  | **Stooq** | — | — | **Ruled out:** robots.txt `Disallow: /`, and CSV downloads sit behind a JavaScript proof-of-work challenge |

  **Price history (A), free and paid**, checked on 2026-10-21 from each provider's
  pricing page and docs (FMP's figures come from search results because its site
  returns 403). Prices are per month in USD unless noted.

  | Provider | Covers for A | Price | Licence and robots.txt |
  |---|---|---|---|
  | **Alpha Vantage** | Free: daily stocks, latest 100 sessions only (docs: "The "full" outputsize is available to premium keys"); full daily FX history; daily crypto; daily WTI and Brent, other commodities monthly (sourced from FRED). Premium adds full daily history, adjusted closes (`TIME_SERIES_DAILY_ADJUSTED`) and 200+ indices (`INDEX_DATA`). Weekly and monthly series carry no premium note | $49.99 (75 requests/minute, no daily limit) up to $249.99 (1,200/minute); yearly $499–$2,499 | As in the table above. The premium page also says "historical index data" needs a separate entitlement via its Alpha X Terminal, which conflicts with `INDEX_DATA` being a premium-key endpoint. Ask before paying for indices |
  | **EODHD** | "Historian" plan: end of day for all its exchanges, 30+ years, with dividends and splits. Its exchange page names US, LSE and XETRA but not SGX, Paris, ASX, NSE, Hong Kong or Tokyo (it says 70+ exchanges are in its `exchanges-list` endpoint). Indices and futures not confirmed | Historian $19.99 ($199/year), 100,000 calls/day; intraday plan $29.99; the fundamentals plan ($59.99) has no prices; all-in-one $99.99 | Non-professional users may "store, manipulate, and analyze" for "private, non-commercial purposes", but not redistribute or display. Nothing on AI. `/api/` disallowed (keyed API, so its terms decide) |
  | **Tiingo** | "Power" plan: same coverage as free (US and Chinese stocks, ETFs, funds, 30+ years); nothing outside the US and China | $30 ($300/year), 10,000/hour, 100,000/day; internal commercial use $50 | Internal use only, as above |
  | **Twelve Data** | "Grow" plan adds end of day for global stocks and ETFs, and commodities (20+ markets); "Pro" 70+ markets. Some exchanges (ASX, Cboe Canada, Cboe Europe) are extra yearly add-ons | Grow $79, Pro $229, Ultra $999; about 17% off yearly | Prices are for personal use; commercial pricing is on a separate page that wasn't read. Terms as in the table above |
  | **FMP** | Starter: US; Premium adds UK and Canada; Ultimate: global. Futures and indices not confirmed | Starter $22, Premium $59, Ultimate $149 (billed yearly); free tier 250 requests/day | Not read (site returns 403) |
  | **Massive** (formerly Polygon) | US stocks only. Its free Basic plan gives 2 years of end of day at 5 requests/minute. Its indices, currency and futures plans weren't read | Starter $29 (5 years), Developer $79 (10 years), Advanced $199 (20+ years) | Plans marked for individual use; business pricing separate. robots.txt has no rules |
  | **Databento** | The only clean source found for futures: daily bars for CME, CBOT, NYMEX and COMEX, 16+ years. Its own calculator shows 30 days of daily bars for under $0.01 | Pay as you go per GB, with $125 of free credits for new users (expire after 6 months); Standard $199 | Licensed per dataset, with personal and commercial use separate; check its licence manager. robots.txt disallows only `/portal` |
  | **CoinGecko** (crypto only) | Daily history: 1 year on the free Demo plan, 2 years on Basic, from 2013 on higher plans | Demo free (10,000 calls/month, 100/minute); Basic $35 ($29 yearly), Analyst $129 | "Powered by CoinGecko" credit required; it discourages caching ("refresh the cache at least every 24 hours"). `api.coingecko.com` disallows `/api/v3` (keyed API, so its terms decide); the main site declares `ai-input=yes, ai-train=no` |
  | **FRED** (free) | US indices, FX and commodity series. Which series and how much history each has weren't checked | Free with a key; no published rate limit | Third-party series ("Copyright" in their notes) need the owner's permission for non-personal use. Apps must show "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis." Nothing on AI. `fred.stlouisfed.org` blocks only graphs and search, with a 1-second crawl delay; `api.stlouisfed.org` timed out from here |
  | **ECB data API** | — | — | **Ruled out:** `data-api.ecb.europa.eu` robots.txt blocks ClaudeBot, Claude-Web, anthropic-ai and ChatGPT-User by name, and also `python-requests` and `curl` |

  So no free option covers the scripts' default windows. Alpha Vantage's 100
  sessions are enough for `stock_price_history.py` (default `1mo`). They are not
  enough for the chart scripts (`6mo`, about 126 sessions) or `stock_risk.py`
  (`1y`) unless those move to weekly bars. **Cheapest paid fit for A:** EODHD
  Historian ($19.99), if its `exchanges-list` confirms the ten exchanges and
  indices. Add Databento for futures. **Single-API fit for A and C–F:** Alpha Vantage
  premium ($49.99). Every personal plan above forbids showing the data to others,
  which matters if either web app is ever served beyond your own machine.

  **Chosen for price history (A)**, 2026-10-21, for stability:
  1. **EODHD Historian** ($19.99) is the main source, for stocks, FX and crypto.
     It is a documented keyed API whose business is end-of-day data, and its terms
     allow personal storage and analysis. Coverage was tested with a free key on
     2026-10-21 (7 of the day's 20 calls). `exchanges-list` returns 70 exchanges,
     including US (`US`), London (`LSE`), XETRA (`XETRA`), Euronext Paris (`PA`),
     Toronto (`TO`), ASX (`AU`), `FOREX` and crypto (`CC`). It has no entry for
     Singapore, India, Hong Kong, Tokyo or indices, and it isn't complete:
     `/api/eod/` returned daily OHLCV with `adjusted_close` for `GSPC.INDX`
     (S&P 500) and `0700.HK`. The other symbols tried all returned 404 "Ticker
     Not Found.": `D05.SG` and `D05.SGX` (DBS), `RELIANCE.NSE` and `7203.TSE`
     (Toyota). Those suffixes were guesses, so Singapore, India and Tokyo may exist
     under other codes, but most likely they aren't covered.
  2. **Databento** (pay as you go) covers futures: CME, CBOT, NYMEX and COMEX
     daily bars, licensed from the exchanges. It sells individual contracts, so a
     Yahoo-style continuous front month (`GC=F`) needs its rolling symbology.
  3. **FRED** (free) is optional, for US indices and commodities, and only if
     EODHD has no indices. Index series are licensed for personal use only, and
     FRED's "not endorsed" notice is required.

  That leaves Singapore (`.SI`), India (`.NS`) and Tokyo (`.T`) uncovered. The
  options are:
  - drop those three markets;
  - send them to Alpha Vantage through a shared module that routes by Yahoo
    suffix, with Databento for `=F` and EODHD for everything else, and converts
    each provider's response to the `extract_series()` shape so the price scripts
    barely change. Free Alpha Vantage gives those markets only about 100 daily
    sessions, short of the charts' `6mo` and `stock_risk.py`'s `1y`. Full history
    takes premium, which makes $69.98/month together with EODHD;
  - use Alpha Vantage premium ($49.99) alone, if it covers all ten exchanges. That
    is one provider and one set of terms, and it can later cover C–F as well;
  - ask EODHD support whether the three markets exist under other codes or plans.

  **Alpha Vantage tested** with a free key (`ALPHAVANTAGE_API_KEY` in `.env`, next
  to `EODHD_API_KEY`) on 2026-10-21, using 17 of the day's 25 calls.
  `TIME_SERIES_DAILY` returned 100 sessions for `AAPL`, `TSCO.LON`, `MBG.DEX`,
  `MC.PAR`, `SHOP.TRT` and `RELIANCE.BSE` (India's Bombay exchange; no NSE
  listing turned up). `outputsize=full` was refused as "a premium feature for the
  TIME_SERIES_DAILY endpoint". `D05.SGX`, `7203.TYO` and `0700.HKG` returned
  "Invalid API call", and `BHP.AUS` returned an empty response (possibly a rate
  limit; inconclusive). Those suffixes were guesses, but `SYMBOL_SEARCH` agrees:
  for DBS, Toyota, Tencent and BHP it returned only US, London, Frankfurt and
  other foreign listings, never a Singapore, Tokyo, Hong Kong or ASX one. For
  Reliance it returned `RELIANCE.BSE`.

  | Market | EODHD | Alpha Vantage |
  |---|---|---|
  | US, London, Germany, Paris, Toronto | yes | yes |
  | ASX | listed, not tested | ? |
  | Hong Kong | yes | no |
  | India | no | yes (BSE listing only) |
  | Singapore, Tokyo | no | no |

  So Alpha Vantage alone is out, and combining the two adds only India. India
  would come from the BSE listing, so `.NS` tickers would map to `.BSE`, whose
  prices differ slightly, and free Alpha Vantage gives only about 100 sessions.
  Singapore and Tokyo need a third provider or must be dropped. Twelve Data Grow
  ($79) and FMP Ultimate ($149) claim global coverage, but neither is confirmed for
  these markets. **Simplest stable setup:** EODHD plus Databento for futures,
  dropping Singapore and Tokyo, and either dropping India or adding free Alpha
  Vantage for it. The agents' DBS (`D05.SI`) examples would need rewriting.

  **Built on 2026-10-21:** `eodhd_price_history.py` and
  `alphavantage_price_history.py`, which share `daily_prices.py`. They take each
  provider's own ticker notation and emit `stock_price_history.py`'s row shape.
  No agent calls them yet.

  **Markets decided on 2026-10-21:** leave out Singapore (`.SI`) and Tokyo (`.T`)
  for now, to revisit later; take India from Alpha Vantage (`.NS` → `.BSE`); take
  everything else from EODHD.

  **Price history moved on 2026-10-21:** `price_source.py` routes Yahoo-style
  tickers to those providers, and the four price scripts and their 5 agents now
  use it. `^GSPC`, `^IXIC` and `^HSI` map to EODHD's `.INDX` codes, but `^FTSE`
  (`FTSE.INDX`) returns no data; EODHD's code for it is still to find. Still to
  do: add Databento for futures; revisit Singapore and Tokyo; replace the
  screener, the `quoteSummary` scripts and the stock web app's quote, which
  still call Yahoo.

  **Alpha Vantage `TOP_GAINERS_LOSERS` tested** for `market_top_volume.py` on
  2026-10-22 with the free key (1 call). It returned three US-wide lists of 20
  rows, `top_gainers`, `top_losers` and `most_actively_traded`, each with
  `ticker`, `price`, `change_amount`, `change_percentage` and `volume`, all as
  strings (`"71.5239%"`). It is a weak fit:
  - It is the last session's close, not live: `last_updated` was
    `2026-10-21 16:15:56 US/Eastern` on the 22nd.
  - The gainers and losers are mostly warrants, preferreds, rights and units
    (`NXGLW`, `AHT-H`, `DSX+`, `HUBCZ`) and sub-$1 stocks: 11 of 20 gainers and
    18 of 20 losers were under $1, and one loser traded 686 shares. Filtering
    those out of 20 rows may leave few. `most_actively_traded` is mostly ordinary
    stocks (6 of 20 under $1).
  - No exchange or company name, so `nyse` / `nasdaq` / `amex` can't be split
    without a lookup per ticker, and `--limit` would cap at 20.

  So it could serve the US `volume` metric, labelled as the last session's
  figures, but not `gainers` or `losers`; those need a paid source or would be
  dropped. Check EODHD's bulk end-of-day and screener APIs for the same problems
  before choosing it for markets outside the US.

  **Other top-mover sources**, checked on 2026-10-22 from each provider's docs
  (none tested with a key). None is free with full coverage, and none is live on
  the free or cheap plans.

  | Source | Volume | Gainers / losers | Markets | Cost | Notes |
  |---|---|---|---|---|---|
  | **EODHD screener** (`/api/screener`) | yes, sort by `avgvol_1d` (last day's volume) | yes, sort by `refund_1d_p` (1-day % change) | `exchange` filter (`us`, `lse`, `to`, …) and `sub_exchange` (NYSE / NASDAQ) | 5 calls per request; EOD+Intraday ($29.99) or All-In-One, not Historian | Returns names; a `market_capitalization` filter could drop warrants and penny stocks. End of day only (`last_day_data_date`). Up to 500 rows per request |
  | **EODHD bulk end of day** | computed by the script | computed by the script | one exchange per request | about 100 calls per exchange (a forum thread, not the pricing page); Historian ($19.99) | No names or market cap |
  | **Twelve Data** `/market_movers/stocks` | no | yes, with name, exchange and a `price_greater_than` filter | `country` filter; up to 50 rows | 100 credits per request; Pro plan ($229) | No volume metric |
  | **Alpaca** `/v1beta1/screener/stocks/most-actives` | yes, by volume or trade count, top 1–100 | not confirmed | US only (SIP) | free plan access unclear; needs an Alpaca account | Symbol, volume and trade count only. Terms not read |
  | **FMP** `actives` / `gainers` / `losers` | yes | yes | probably US only | free tier unclear | Terms not read (site returns 403 to automated fetches) |

  Exchanges' own websites (Nasdaq.com, LSE, …) weren't checked; they would be page
  scraping, not a documented API, and need their own robots.txt and terms check.
  **Best fit:** the EODHD screener on EOD+Intraday ($29.99, $10 more than
  Historian), which covers all three metrics, the NYSE / NASDAQ split, names and a
  market-cap filter on one provider. Before choosing it, confirm which non-US
  exchanges it covers and whether its 1-day % change has Alpha Vantage's
  junk-ticker problem.

  **Data functions a replacement must provide**, listed on 2026-10-22 from the
  fields the stock scripts, their agents and `app/stock_information/` read. Only
  1 has moved off Yahoo; 4–15 come from `quoteSummary` today.

  | # | Function | Returns | Used by | Source now |
  |---|---|---|---|---|
  | 1 | `daily_history(symbol, start, end)` | daily open, high, low, close, adjusted close, volume; exchange, currency | `stock_price_history.py`, `stock_candlestick_chart.py`, `stock_rebased_chart.py`, `stock_risk.py`, `stock-trend` agent | done: `price_source.fetch_history()` |
  | 2 | `quote(symbol)` | latest price, session date, day high and low, previous close, change, 52-week high and low; name, exchange, currency | `app/stock_information/` | Yahoo chart |
  | 3 | `top_movers(market, metric, limit)` | rank, symbol, name, exchange, volume, price, % change, currency; by volume, gainers or losers | `market_top_volume.py`, `stock_tech_buzz_agent.py` | Yahoo screener |
  | 4 | `profile(symbol)` | name, exchange, quote and reporting currency, sector, industry | all five `quoteSummary` scripts | Yahoo |
  | 5 | `fundamentals(symbol)` | price, market cap, shares outstanding, enterprise value; revenue, EBITDA, net income, free and operating cash flow, trailing and forward EPS, book value per share; gross, operating and profit margins, ROE, ROA, revenue and earnings growth, current and quick ratios, debt to equity, total debt and cash; trailing and forward P/E, P/S, P/B, EV/EBITDA, beta, dividend yield, payout ratio | `stock_intrinsic_value.py`, `stock_fundamental.py`, the app | Yahoo |
  | 6 | `growth_estimates(symbol)` | analysts' 1-year and 5-year growth | `stock_intrinsic_value.py` (and `stock_fundamental.py`) | Yahoo |
  | 7 | `next_earnings(symbol)` | next report date or range, confirmed or estimated, time, EPS and revenue estimates (low, average, high) | `stock_earnings_calendar.py` | Yahoo |
  | 8 | `earnings_history(symbol)` | per recent quarter: quarter end, fiscal quarter, report date, EPS estimate and actual, surprise % | `stock_earnings_calendar.py` | Yahoo |
  | 9 | `dividends(symbol)` | next ex-dividend and payment dates, last amount and date | `stock_earnings_calendar.py` | Yahoo |
  | 10 | `analyst_targets(symbol)` | target low, median, mean, high; number of analysts; consensus rating and mean score | `stock_analyst_targets.py` | Yahoo |
  | 11 | `recommendation_trend(symbol)` | strong buy / buy / hold / sell / strong sell counts for this month and the 3 before | `stock_analyst_targets.py` | Yahoo |
  | 12 | `analyst_actions(symbol, days)` | per action: date, firm, action, from and to grade, target change, new and prior target | `stock_analyst_targets.py` | Yahoo |
  | 13 | `ownership_summary(symbol)` | % held by insiders and institutions (of shares and of float), number of institutions | `stock_holders.py` | Yahoo |
  | 14 | `insider_transactions(symbol, days)` | per trade: insider and role, date, shares, value, description (sale, purchase, gift, award…), direct or indirect | `stock_holders.py` | Yahoo |
  | 15 | `top_holders(symbol, kind)` | biggest fund or institutional holders: name, % held, shares, value, change, report date | `stock_holders.py` | Yahoo |

  - 4–6, 7–9, 10–12 and 13–15 each come from one `quoteSummary` call now; a
    provider that needs several requests per group costs more of a free quota.
  - `stock_holders.py` asks for institutional holders only on US listings, and
    insider trades are in USD only there. A replacement may cover 13–15 for the US
    only (e.g. SEC EDGAR).
  - Optional: `symbol_search(name)` (e.g. Alpha Vantage `SYMBOL_SEARCH`). The
    scripts don't need it, since the agents resolve tickers, but it could replace
    guessed exchange suffixes.
  - No free replacement found yet (2026-10-20 shortlist): 3 outside the US, 12, and
    most of 15.

  **Recommended:** Alpha Vantage as the single provider (a shared module in place
  of `yahoo_finance.py`, with `ALPHAVANTAGE_API_KEY` in `.env`), SEC EDGAR later for
  US fundamentals and insider data to save Alpha Vantage requests. **No free
  replacement** for: top movers outside the US, analyst upgrade / downgrade
  history, most fund-holder lists, index and adjusted history on free tiers,
  futures (`=F`). At 25 requests a day, a fundamentals lookup (4–5 calls) is a
  real share of the budget.

  **Decisions needed before building:** whether a free Alpha Vantage key and its
  limits (25 requests a day, 100 daily sessions) are acceptable, or which paid plan
  to take; which uncovered features to drop or which scripts to
  remove; what contact to declare to the SEC, if EDGAR is added. Re-check Finnhub
  and FMP with a real key, since their free tiers couldn't be confirmed.

## Top picks

Chosen on 2026-10-21, in suggested order (the 2026-10-19 picks, the broken-link
checker and the `web-search` test runs, are done). Each is described in full in its
section below; remove it from both places when it's done.

All the 2026-10-21 picks are done too (trip weather, the `url-summary` test runs and
the RSS/Atom feed reader). Choose the next ones from the sections below.

## Combining existing scripts

No new data source, so nothing new to vet; mostly agent work or small glue scripts.

- [ ] **Stock deep-dive agent**: one request chains fundamentals, intrinsic value,
  analyst targets, holders, the earnings calendar and the trend for one ticker into
  a single report, the way the research summary agent chains its tools.

## Weather and environment

All Open-Meteo endpoints are free and keyless. They can reuse `weather.geocode()`,
`fetch_json()` and `place_fields()`.

- [ ] **Marine forecast** (Open-Meteo marine API): wave height, swell, sea temperature
  for coastal places.
- [ ] **River flood forecast** (Open-Meteo flood API): river discharge levels.
- [ ] **Climate projections and elevation** (Open-Meteo climate and elevation APIs):
  long-range temperature and rainfall projections for a place, and its height above
  sea level.
- [ ] **Earthquakes near a place** (USGS GeoJSON feed, free): recent quakes filtered by
  magnitude and distance from the coordinates `geocode()` returns.
- [ ] **Space weather and aurora** (NOAA Space Weather Prediction Center JSON
  products): the current and forecast Kp index and aurora outlook, and whether
  aurora might be visible at a place's latitude.
- [ ] **Tides** (NOAA CO-OPS tide predictions, US stations): high and low tides for
  the station nearest a place.

## Finance

### Extending existing scripts

- [ ] **More use of the risk metrics**: `stock_risk.py` and the `stock-risk` agent
  report `indicators.py`'s `volatility`, `max_drawdown` and `correlation`. The
  `stock-trend` agent could add a line of volatility and worst drawdown alongside
  its verdict (reusing `stock_risk.periods_per_year()` for crypto), and the
  `stock-rebased-chart` agent could run `stock_risk.py` on the same symbols when the
  user asks how closely they moved together. Shading the worst drawdown on the
  candlestick chart is a further option.
- [ ] **Dividend and split history**: Yahoo's chart endpoint can return dividend and
  split events alongside prices (`events=div,splits`), so this is an extension of
  `yahoo_finance.py`. Unofficial, like the rest of Yahoo.

### New sources

- [ ] **FX rates from Frankfurter** (ECB reference rates, no key): an official
  alternative to Yahoo for currency conversion.
- [ ] **SEC EDGAR filings** (free; requires a descriptive User-Agent header): recent
  10-K / 10-Q / 8-K filings for US companies.
- [ ] **Macro data**: World Bank API (no key) or FRED (free key) for GDP, inflation,
  interest rates.

## Tech and news

### Extending existing scripts

- [ ] **HN user profiles**: karma, account age, "about" text and recent submissions
  for a username, from the official HN API's user endpoint; reuses `hn.py`.

### New sources

- **Vulnerability lookup (OSV.dev): checked and built.** Checked on 2026-10-20 and
  built the same day as `osv_vulnerabilities.py` and the `package-vulnerabilities`
  agent. The check, kept for the record:
  - **robots.txt:** `osv.dev/robots.txt` is only a `Sitemap:` line, with no
    `Disallow` rules for any client. `api.osv.dev` has no robots.txt (404).
  - **AI signals:** none found. There is no `Content-Signal` line, no `X-Robots-Tag`
    header (on the site or the API), no robots or TDM meta tags on the home page, and
    no `ai.txt` or `.well-known/tdmrep.json`.
  - **API terms:** the API docs and FAQ give no terms of use, need no key, and say
    "Currently there are no limits on the API" (responses are capped at 32 MiB over
    HTTP/1.1). Endpoints: `POST /v1/query`, `POST /v1/querybatch`,
    `GET /v1/vulns/{id}` on `api.osv.dev`. The osv.dev code is Apache 2.0.
  - **Data licence:** there is no single licence; the data page licenses each source
    separately. Most are CC-BY 4.0 (GitHub, PyPI, Go, OSS-Fuzz, PSF), some CC0
    (RustSec, GSD, Haskell, opam), MIT, BSD or Apache 2.0, and Ubuntu is CC-BY-SA 4.0.
    CC-BY needs attribution, so the script and agent should credit the advisory's
    source (its ID prefix, e.g. `GHSA-`, `PYSEC-`, `GO-`, `RUSTSEC-`) and link each
    advisory's osv.dev page.
  - **Courtesy:** no limit is published, but keep requests small: one `query` per
    package (or one `querybatch`), and no bulk crawling. For whole databases OSV
    publishes data dumps instead.
- [ ] **Package stats**: PyPI's JSON API (versions, release dates, metadata) and
  npm's registry and downloads APIs.
- [ ] **GitHub releases**: the latest releases of a repository, from the GitHub API
  (unauthenticated requests are rate-limited); pairs with GitHub "trending" below.
- [ ] **Stack Exchange search** (Stack Exchange API): questions and answers about a
  topic; a small daily quota without a key.
- [ ] **GitHub "trending"**: GitHub search API, e.g. repos created in the last 7 days
  sorted by stars. There is no official trending endpoint, and unauthenticated
  requests are rate-limited.
- [ ] **arXiv new papers** (arXiv API, no key): latest papers in categories like
  cs.AI and cs.LG.
- [ ] **More discussion sources** beyond Hacker News: check the site's robots.txt
  and terms before building anything (see CLAUDE.md). Checked on 2026-10-19:
  - **Lobsters: ruled out.** It was added (`8dbf161`) and removed the same day
    (`107e24a` was the last commit with it). Its robots.txt disallows the whole site
    (`User-agent: *` / `Disallow: /`, with a comment asking clients to follow the
    standard honestly), disallows `/search` and `/page/` even for the named search
    engines it allows, and declares `Content-Signal: ai-input=no, ai-train=no`. The
    repo fetched its JSON feeds and fed them to an AI model, so all Lobsters support
    (`lobsters.py`, `lobsters_thread.py`, the `--source lobsters` option, the
    `lobsters-thread` agent, and Lobsters in the summary agent and web app) was
    removed, and a Lobsters search script was dropped before it was built.
  - **Reddit:** its JSON returns 403 without OAuth.
  - **Dev.to:** its API works without a key, but its top items are posts on dev.to
    itself rather than links with a discussion.
- [ ] **Wikipedia**: REST summary API for a quick topic summary, page-views API for
  "what's trending on Wikipedia today".

## Web pages (extending the `url_*` family)

- [ ] **HTTP and security headers**: report a URL's HSTS, Content-Security-Policy,
  caching and server headers, as a small `url_*` sibling.
- [ ] **Wayback history**: list a page's archived snapshots over time from the
  Wayback Machine's CDX API, extending what `url_availability.py --wayback` does.
- [ ] **SSL certificate expiry and DNS lookup**: standard library only (`ssl`, `socket`).
- [ ] **robots.txt and sitemap listing**.

## Repo and tooling

- [ ] **More targeted test runs**: `docs/features/agent/hottest-tech-discussion-summary/test-runs.md`
  has caught real edge cases in the research summary agent. The same approach (a
  fixed input per judgement rule, with pass criteria) could cover other agents with
  judgement steps. `web-search`, `url-summary` and `hn-search` got theirs on 2026-10-21
  (`docs/features/agent/<agent>/test-runs.md`). Still untested: `web-search` with a real
  quota message or an empty result list, `url-summary`'s `ai-input=no` note (no live
  site found that sets it for every client), and `hn-search`'s invalid-argument path
  (seen once in a rerun, handled correctly). `trip-weather` and `url-feed` got theirs on 2026-10-21 too; they found
  Open-Meteo's daylight-saving error in sun times (fixed in `weather.local_daily()`)
  and a `--since` run cut short by the default `--limit` (fixed in the agent).
  `package-vulnerabilities` got its runs on 2026-10-21 as well; all passed, with no
  changes needed. Still without runs: `air-quality` (its new `--forecast`) and
  `url-broken-links`. The fixes to `hn-search`, `trip-weather` and `url-feed` were
  confirmed by reruns on 2026-10-21, which also added an `--author` case to `hn-search`
  and an ambiguous-place case to `trip-weather`.
