# Things to explore

A backlog of data sources and features that could be added on top of the existing
scripts. Nothing here is implemented yet, and none of the API claims below have
been verified. Check the endpoint, its terms, its robots.txt and whether it needs a
key before building on it (see the Lobsters note under "More discussion sources"
for why).

Ideas that reuse an existing shared module (`weather.py`, `yahoo_finance.py`,
`url_*.py`) are listed first in each section, because they need the least new code.

When one of these is implemented, follow the usual repo conventions: script + tests
+ agent + feature specs (`docs/features/script/...`, `docs/features/agent/...`) +
both READMEs in the same change. Then remove the item from this list.

## Top picks

Chosen on 2026-10-19, in suggested order. Each is described in full in its section
below; remove it from both places when it's done.

1. **Vulnerability lookup via OSV.dev** (Tech and news): the most useful new source,
   and the first one to go through the robots.txt-and-terms check before anything is
   built; record the finding here either way.
2. **Broken-link checker** (Combining existing scripts): joins `url_links.py` and
   `url_availability.py`; the main design question is staying polite on big pages (a
   cap on links, a delay, each host checked sparingly).
3. **Targeted test runs for `web-search`** (Repo and tooling): every research flow
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

- [ ] **Use the risk metrics**: `indicators.py` now has `volatility`,
  `max_drawdown` and `correlation`, but nothing calls them yet. The `stock-trend`
  agent could mention volatility and the worst drawdown alongside its verdict, and
  the rebased chart (or a new agent) could report the correlation between the
  tickers it compares, after lining up their shared dates.
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

- [ ] **Vulnerability lookup** (OSV.dev, no key): known vulnerabilities for a package
  and version across PyPI, npm, Go, crates.io and other ecosystems.
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
