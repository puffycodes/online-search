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
  | **Alpha Vantage** | A (global stocks, FX, crypto, a few commodities; adjusted closes and indices are paid), B (US only), C, D, E (target and rating counts only), F | 25 requests/day; unlimited for verified open-source or educational projects | Free use is "personal, non-commercial" for "investment analysis, research, testing, monitoring"; nothing on AI, and its docs promote use with LLMs and agents (official MCP server). No robots.txt |
  | **SEC EDGAR** (`data.sec.gov`) | C and F for US filers only (XBRL company facts, Form 4, 13F); no prices or estimates | No key; 10 requests/second | Free to "access and download"; declare a name and contact email in the User-Agent. `data.sec.gov` has no robots.txt; `sec.gov` disallows only search, admin and login paths |
  | **Finnhub** | C, D, E (recommendation trends); price history reportedly paid; rest ? | 60/minute; free endpoints unconfirmed | "Strictly for personal use"; no redistributing data "or derived results"; nothing on AI |
  | **Twelve Data** | A (US stocks, FX, crypto only); C–F paid | 800/day, 8/minute | No commercial use of free-tier data, no redistribution or external display, no caching beyond documented limits; nothing on AI. API host robots.txt is `Disallow: /`, but it's a documented keyed API, so its terms decide |
  | **EODHD** | A (global end of day); rest ? | ? | Non-professional users may "store, manipulate, and analyze" but not redistribute or display; nothing on AI. `/api/` disallowed in robots.txt (same reasoning as Twelve Data) |
  | **Tiingo** | A (US, FX, crypto); fundamentals paid | 1,000/day, 50/hour, 500 symbols/month (third-party figures) | Terms not read (page 404) |
  | **FMP** | C–F claimed; ? | ? | Terms not read (403 to automated fetches); display or redistribution needs a separate licence |
  | **Massive** (formerly Polygon) | US only | ? | Only the terms index was read |
  | **Stooq** | — | — | **Ruled out:** robots.txt `Disallow: /`, and CSV downloads sit behind a JavaScript proof-of-work challenge |

  **Recommended:** Alpha Vantage as the single provider (a shared module in place
  of `yahoo_finance.py`, with `ALPHAVANTAGE_API_KEY` in `.env`), SEC EDGAR later for
  US fundamentals and insider data to save Alpha Vantage requests. **No free
  replacement** for: top movers outside the US, analyst upgrade / downgrade
  history, most fund-holder lists, index and adjusted history on free tiers,
  futures (`=F`). At 25 requests a day, a fundamentals lookup (4–5 calls) is a
  real share of the budget.

  **Decisions needed before building:** whether a free Alpha Vantage key and its
  limit are acceptable; which uncovered features to drop or which scripts to
  remove; what contact to declare to the SEC, if EDGAR is added. Re-check Finnhub
  and FMP with a real key, since their free tiers couldn't be confirmed.

## Top picks

Chosen on 2026-10-19, in suggested order. Each is described in full in its section
below; remove it from both places when it's done.

1. **Broken-link checker** (Combining existing scripts): joins `url_links.py` and
   `url_availability.py`; the main design question is staying polite on big pages (a
   cap on links, a delay, each host checked sparingly).
2. **Targeted test runs for `web-search`** (Repo and tooling): every research flow
   depends on it, and its fallback rules (missing key, quota message, transient
   error) have never been tested on purpose.

## Combining existing scripts

No new data source, so nothing new to vet; mostly agent work or small glue scripts.

- [ ] **Broken-link checker**: run `url_links.py` on a page, check each link with
  `url_availability.py`, and offer `--wayback` copies of the dead ones. Mind the
  number of requests on a page with hundreds of links (a cap and a delay).
- [ ] **Stock deep-dive agent**: one request chains fundamentals, intrinsic value,
  analyst targets, holders, the earnings calendar and the trend for one ticker into
  a single report, the way the research summary agent chains its tools.
- [ ] **Trip weather**: forecast, air quality and pollen, UV and daylight for a place
  and a date range ("what's Paris like next week?"), from the existing weather
  scripts.

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
- [ ] **RSS/Atom feed reader**: latest items from a site's feed.
- [ ] **SSL certificate expiry and DNS lookup**: standard library only (`ssl`, `socket`).
- [ ] **robots.txt and sitemap listing**.

## Repo and tooling

- [ ] **More targeted test runs**: `docs/features/agent/hottest-tech-discussion-summary/test-runs.md`
  has caught real edge cases in the research summary agent. The same approach (a
  fixed input per judgement rule, with pass criteria) could cover other agents with
  judgement steps: `url-summary`, `hn-search`'s opinion sampling, and `web-search`'s
  fallback choice.
