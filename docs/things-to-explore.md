# Things to explore

A backlog of data sources and features that could be added on top of the existing
scripts. Nothing here is implemented yet, and none of the API claims below have
been verified. Check the endpoint, its terms and whether it needs a key before
building on it.

Ideas that reuse an existing shared module (`weather.py`, `yahoo_finance.py`,
`url_*.py`) are listed first in each section, because they need the least new code.

When one of these is implemented, follow the usual repo conventions: script + tests
+ agent + feature specs (`docs/features/script/...`, `docs/features/agent/...`) +
both READMEs in the same change. Then remove the item from this list.

## Top picks

None chosen right now; pick the next ones from the sections below.

## Weather and environment

All Open-Meteo endpoints are free and keyless. They can reuse `weather.geocode()`,
`fetch_json()` and `place_fields()`.

- [ ] **Marine forecast** (Open-Meteo marine API): wave height, swell, sea temperature
  for coastal places.
- [ ] **River flood forecast** (Open-Meteo flood API): river discharge levels.
- [ ] **Earthquakes near a place** (USGS GeoJSON feed, free): recent quakes filtered by
  magnitude and distance from the coordinates `geocode()` returns.

## Finance

### New sources

- [ ] **FX rates from Frankfurter** (ECB reference rates, no key): an official
  alternative to Yahoo for currency conversion.
- [ ] **SEC EDGAR filings** (free; requires a descriptive User-Agent header): recent
  10-K / 10-Q / 8-K filings for US companies.
- [ ] **Macro data**: World Bank API (no key) or FRED (free key) for GDP, inflation,
  interest rates.

## Tech and news

### New sources

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

- [ ] **RSS/Atom feed reader**: latest items from a site's feed.
- [ ] **SSL certificate expiry and DNS lookup**: standard library only (`ssl`, `socket`).
- [ ] **robots.txt and sitemap listing**.
