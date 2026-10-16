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

1. **Earlier HN threads in the research summary** (Extending `hn_search.py`):
   instructions-only change to the `hottest-tech-discussion-summary` agent, but it
   lengthens an already multi-step workflow. Open questions: search only or also read
   the top earlier thread, always on or on request, and how far back counts as earlier.

## Weather and environment

All Open-Meteo endpoints are free and keyless. They can reuse `weather.geocode()`,
`fetch_json()` and `place_fields()`.

- [ ] **Pollen levels**: part of the Open-Meteo air-quality API (Europe only). Could be
  added to `air_quality.py`.
- [ ] **Marine forecast** (Open-Meteo marine API): wave height, swell, sea temperature
  for coastal places.
- [ ] **River flood forecast** (Open-Meteo flood API): river discharge levels.
- [ ] **Earthquakes near a place** (USGS GeoJSON feed, free): recent quakes filtered by
  magnitude and distance from the coordinates `geocode()` returns.

## Finance

### Yahoo `quoteSummary`: more modules (reuse `yahoo_finance.fetch_quote_summary()`)

- [ ] **Insider transactions and major holders** (`insiderTransactions`, `majorHoldersBreakdown`)

### New sources

- [ ] **FX rates from Frankfurter** (ECB reference rates, no key): an official
  alternative to Yahoo for currency conversion.
- [ ] **SEC EDGAR filings** (free; requires a descriptive User-Agent header): recent
  10-K / 10-Q / 8-K filings for US companies.
- [ ] **Macro data**: World Bank API (no key) or FRED (free key) for GDP, inflation,
  interest rates.

## Tech and news

### Extending `hn_search.py`

- [ ] **Earlier HN threads in the research summary**: let the
  `hottest-tech-discussion-summary` agent run `hn_search.py` for each trending topic,
  to add how HN discussed it before.

### New sources

- [ ] **GitHub "trending"**: GitHub search API, e.g. repos created in the last 7 days
  sorted by stars. There is no official trending endpoint, and unauthenticated
  requests are rate-limited.
- [ ] **arXiv new papers** (arXiv API, no key): latest papers in categories like
  cs.AI and cs.LG.
- [ ] **More discussion sources**: Lobsters, Reddit and Dev.to JSON feeds, possibly
  merged into `hottest_tech_discussions.py` so it covers more than Hacker News.
- [ ] **Wikipedia**: REST summary API for a quick topic summary, page-views API for
  "what's trending on Wikipedia today".

## Web pages (extending the `url_*` family)

- [ ] **Page titles in `url-summary`**: have the agent also run `url_metadata.py` per
  URL to label each summary with the page's title (`url_content.py --text` keeps the
  title only as unlabelled text at the start of `content`). Instructions-only, but
  doubles the fetches per URL.
- [ ] **RSS/Atom feed reader**: latest items from a site's feed.
- [ ] **SSL certificate expiry and DNS lookup**: standard library only (`ssl`, `socket`).
- [ ] **robots.txt and sitemap listing**.
