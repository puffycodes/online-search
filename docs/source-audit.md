# Source audit

A check of every outside service the scripts call, against its robots.txt and its
terms of use. Run on **2026-10-20**. Robots.txt files were fetched directly that day;
terms were read on the services' own pages (linked below). Rerun it when adding a
source (see CLAUDE.md) or when a service's terms change, and update this page.

**Standard used.** The same one that removed Lobsters on 2026-10-19 (see
[`things-to-explore.md`](things-to-explore.md)): a wildcard `Disallow: /` or an AI
opt-out on what we fetch, or terms that forbid automated access, rule a source out.
A robots.txt on a host that serves a *documented, offered* API is read as aimed at
crawlers; for those the API's own terms decide.

## Summary

| Source | Used by | Verdict | Action |
|---|---|---|---|
| Yahoo Finance (chart, screener, quoteSummary) | `yahoo_finance.py`, the `quoteSummary` `stock_*.py` scripts, `market_top_volume.py`, `stock_tech_buzz_agent.py`, `app/stock_information/`, 6 agents | **Violates** robots.txt and terms | **Open:** price history moved to EODHD / Alpha Vantage on 2026-10-21 (`price_source.py`), with Yahoo back as an opt-in (`PRICE_PROVIDER=yahoo`, off by default) since 2026-10-26; the rest still to remove or replace |
| `ddgs` default `"auto"` backend | `web_search_duckduckgo.py` | **Violated** robots.txt of Google, Yahoo, Startpage, Mojeek, Grokipedia | **Fixed** 2026-10-20: backend pinned to DuckDuckGo |
| DuckDuckGo HTML results | `web_search_duckduckgo.py` | Grey area: allowed by robots.txt, no search API offered | Kept, last in the `web-search` chain |
| Open-Meteo | `weather.py`, `weather_forecast.py`, `weather_history.py`, `air_quality.py`, 4 agents | Allowed; **attribution was missing** | **Fixed** 2026-10-20: CC BY 4.0 credit on every result |
| Pages fetched by the `url_*.py` scripts | `url-*` agents, `hottest-tech-discussion-summary` | No robots.txt or AI opt-out check | **Fixed** 2026-10-20 for agent-chosen pages: `url_content.py --respect-robots`, always used by the research agent |
| Hacker News API (Firebase) | `hn.py` and the HN scripts | Allowed | None |
| HN Search (Algolia) | `hn_search.py`, `hn_thread.py` | Allowed, 10,000 requests/hour/IP | None |
| OSV.dev | `osv_vulnerabilities.py` | Allowed; per-source licences, mostly CC BY 4.0 | Credit already built in |
| Internet Archive (Wayback availability API) | `url_availability.py --wayback` | Allowed | None |
| Brave Search API | `web_search_brave.py` | Allowed (keyed) | None; don't store results or train on them |
| Serper | `web_search_serper.py` | Allowed (keyed); a B2B service | None |
| Tavily | `web_search_tavily.py` | Allowed (keyed) | None |
| SerpApi | `web_search_serpapi.py` | Allowed (keyed) | None |
| Exa | `web_search_exa.py` | Allowed (keyed) | None; don't redistribute retrieved content |
| Perplexity API | `web_search_perplexity.py` | Allowed (keyed) | None |
| EODHD end-of-day API | `eodhd_price_history.py`, and through `price_source.py` the four price scripts and 5 agents (added 2026-10-21) | Allowed (keyed); personal, non-professional use | None; don't redistribute or display the data to others |
| Alpha Vantage | `alphavantage_price_history.py`, and through `price_source.py` Indian tickers in the four price scripts (added 2026-10-21) | Allowed (keyed); personal, non-commercial use | None |
| Frankfurter | `exchange_rates.py` (checked and added 2026-10-27) | Allowed; no key, no quotas; blended rates free to use | Use the blended rates; a single provider's rates follow that provider's terms |
| USGS earthquake catalog (ComCat) | Nothing yet (checked 2026-10-27 for the planned earthquakes script) | Allowed; no key; US-government public domain | Credit the USGS as the source |

## Violations

### Yahoo Finance — open

- **robots.txt:** `query1.finance.yahoo.com` and `query2.finance.yahoo.com`, the API
  hosts the scripts call, both say `User-agent: *` / `Disallow: /`.
  `finance.yahoo.com` (fetched for the consent cookie) disallows `/` to a long list
  of AI agents by name, including `anthropic-ai`, `ClaudeBot` and `Claude-Web`.
- **Terms of service** ([legal.yahoo.com](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)):
  §2(d) forbids to "access or collect data, or attempt to access or collect data,
  from our Services using any automated means… for any purpose without our
  express, prior permission"; §2(e) forbids accessing the services "using a method
  other than the interface and the instructions that we provide".
- The endpoints are undocumented; Yahoo offers no public API for them.
- **Verdict:** fails the same test as Lobsters. Removing it takes out the whole
  stock section (10 scripts, 11 agents, `stock_tech_buzz_agent.py`, the stock web
  app), so the decision is the user's. A replacement price source needs its own
  robots.txt-and-terms check first. Tracked in [`things-to-explore.md`](things-to-explore.md),
  with a replacement shortlist checked on 2026-10-20 (Alpha Vantage recommended,
  SEC EDGAR as a US supplement, Stooq ruled out), and the paid and free
  price-history options checked on 2026-10-21 (ECB data API ruled out). On
  2026-10-21 the four price scripts (`stock_price_history.py`, the two chart
  scripts and `stock_risk.py`) and their 5 agents moved to EODHD and Alpha
  Vantage through `price_source.py`; the screener, `quoteSummary` scripts and the
  stock web app's quote still call Yahoo. On 2026-10-26 the user asked for Yahoo
  price history back as a switch: `PRICE_PROVIDER=yahoo` in `.env` sends
  `stock_data.daily_history()` to `yahoo_finance.daily_history()`. It is off by
  default, and every result it serves carries a note that Yahoo fails this audit.

### `ddgs` "auto" backend — fixed

`web_search_duckduckgo.py` called `DDGS().text()` without a backend. In `ddgs`
9.16.0 that means `"auto"`: a metasearch that tries, in random order, Wikipedia,
Grokipedia, Brave, DuckDuckGo, Google, Mojeek, Startpage and Yahoo. Their
robots.txt files (for `User-agent: *`):

| Engine and path `ddgs` fetches | robots.txt |
|---|---|
| `www.google.com/wml/search` | `Disallow: /search`, `Disallow: /wml/search?`; Google's terms also forbid automated queries |
| `search.yahoo.com/search` | `Disallow: /search`; also blocks `anthropic-ai`, `Claude-Web`, `ClaudeBot` by name |
| `www.startpage.com/sp/search` | `Disallow: /sp/` |
| `www.mojeek.com/search` | `Disallow: /search` |
| `grokipedia.com/api/typeahead` | `Disallow: /api/` |
| `search.brave.com/search` | not readable (HTTP 429) |
| `html.duckduckgo.com/html/` | `Allow: /` |
| Wikipedia `w/api.php?action=opensearch` | a public API |

**Fix:** the backend is now pinned to `"duckduckgo"` (`"html"` for the legacy
`duckduckgo_search` package), with a test that it stays pinned. Side effect:
DuckDuckGo alone rate-limits sooner (`202` after a few quick queries), which "auto"
had been hiding by falling through to the other engines.

**DuckDuckGo itself is a grey area.** `html.duckduckgo.com` allows `/` (its comment
says so that crawlers see its noindex tags), and its
[terms](https://duckduckgo.com/terms) and
[acceptable use policy](https://duckduckgo.com/acceptable-use) don't name automated
queries, but bar interfering "with the integrity or performance of the services",
and DuckDuckGo offers no search API. The script stays last in the `web-search`
fallback chain, after five keyed APIs; dropping it from the chain is the stricter
option.

## Missing attribution

### Open-Meteo — fixed

- [Terms](https://open-meteo.com/en/terms): the data is CC BY 4.0; free use is for
  non-commercial purposes, under 10,000 calls a day, 5,000 an hour and 600 a minute.
- `api.open-meteo.com/robots.txt` is `Disallow: /`, but the API is documented and
  offered for public use, so its terms are what apply.
- **Fix:** all four scripts end their report with `Data by Open-Meteo.com
  (https://open-meteo.com/), licensed under CC BY 4.0.` and add it to the JSON as
  `attribution` (`weather.ATTRIBUTION`); the four agents end their reports with a
  credit line.

## Fetching pages

### Pages fetched by the `url_*.py` scripts — fixed for agent-chosen pages

The four `url_*.py` scripts fetch the page they're given, with an honest
`online-search-url-*` User-Agent, but never read robots.txt or a `Content-Signal`
line. For a URL the user names, that is a user-directed fetch, like a browser. But
`hottest-tech-discussion-summary` picks article URLs itself and feeds the pages to an
AI model, which is the use Lobsters' `ai-input=no` opted out of.

**Fix:** `url_content.py --respect-robots` (via the new `robots.py`) reads the
site's robots.txt by RFC 9309 and its `Content-Signal` lines first, and refuses a
page that is disallowed, opted out of AI input, or whose robots.txt can't be read;
a redirect to another page is checked too. `hottest-tech-discussion-summary` passes
it on every fetch and reports a refused page's link as "blocked by the site's
robots.txt". A URL the user names is still fetched without it, as a user-directed
fetch; for that middle case, the `url-content` and `url-summary` agents pass
`--warn-robots`: the page is still fetched, and a site that opts out of AI input
(`Content-Signal: ai-input=no`) or whose robots.txt asks automated clients not to
fetch the page gets a one-line note in the report. (The second note is what
catches Lobsters: its `ai-input=no` applies only to the search engines it names.)

`url_feed.py` (added 2026-10-21) reads RSS / Atom feeds with the same `--respect-robots`
/ `--warn-robots` pair as `url_content.py`, checking both a page and the feed it
advertises. The `url-feed` agent passes `--respect-robots` when it picks a site's
feed itself and `--warn-robots` for a URL the user gave.

`url_broken_links.py` (added 2026-10-21) fetches the links it finds on a page,
so it reads each linked host's robots.txt once and skips any link disallowed for
`online-search-url-broken-links`; an unreadable robots.txt counts as a full
disallow (RFC 9309). It also spaces requests to one host at least a second apart
and caps the links checked. The page itself, the user's choice, is fetched and
its robots.txt only reported on, as with `--warn-robots`.

## Allowed

- **Hacker News API** ([docs](https://github.com/HackerNews/API)):
  `hacker-news.firebaseio.com/robots.txt` allows `/*.json$`; "There is currently no
  rate limit." The scripts only link to `news.ycombinator.com`, never fetch it.
- **HN Search by Algolia** ([api](https://hn.algolia.com/api)): no robots.txt
  (404); the API page says "We are limiting the number of API requests from a
  single IP to 10,000 per hour."
- **OSV.dev**: checked 2026-10-20 before building `osv_vulnerabilities.py`; see its
  entry in [`things-to-explore.md`](things-to-explore.md).
- **Internet Archive**: `archive.org/robots.txt` disallows only `/control/` and
  `/report/`; the Wayback availability API is public.
- **Brave Search API** ([terms](https://api-dashboard.search.brave.com/terms-of-service)):
  results may be used "with the Customer Applications", AI included; forbidden are
  storing them beyond "transient storage", redistributing them, and using them "to
  create, evaluate, train, re-train, fine-tune, benchmark" AI models.
- **Serper** ([terms](https://serper.dev/terms)): permitted through the API; no
  mirroring of results; describes itself as "a business-to-business service" that
  "does not provide end-user (consumer) services", so personal use is a little grey.
- **Tavily** ([terms](https://tavily.com/terms)): for use in customer applications,
  including AI tools; no training competing models on its output, no relying on it
  alone for high-risk automated decisions.
- **SerpApi** ([legal](https://serpapi.com/legal)): permitted through the API; it
  takes on liability for collecting the search data (its "Legal Shield", which
  excludes the Free, Starter and Developer plans).
- **Exa** ([terms, PDF](https://exa.ai/assets/Exa_Labs_Terms_of_Service.pdf)): the
  only version found is old; it bars copying or redistributing retrieved content
  without permission. The script only displays results.
- **Perplexity API** ([terms](https://www.perplexity.ai/hub/legal/perplexity-api-terms-of-service)):
  output may be displayed "solely within the Customer Applications"; the customer
  owns it.
- **EODHD** ([terms](https://eodhd.com/financial-apis/terms-conditions)): checked
  2026-10-21 before building `eodhd_price_history.py`. Non-professional users may
  "store, manipulate, and analyze the data for private, non-commercial purposes"
  but not redistribute or display it; nothing on AI. `eodhd.com/robots.txt`
  disallows `/api/`, but it's a documented keyed API, so its terms decide (the
  standard above). Full check in [`things-to-explore.md`](things-to-explore.md).
- **Alpha Vantage** ([terms](https://www.alphavantage.co/terms_of_service/)):
  checked 2026-10-20 and 2026-10-21 before building `alphavantage_price_history.py`.
  Free use is "personal, non-commercial"; nothing against AI, and its docs promote
  use with LLMs and agents. No robots.txt (404). Full check in
  [`things-to-explore.md`](things-to-explore.md).
- **Frankfurter** ([docs](https://frankfurter.dev/)): checked 2026-10-27 before
  building `exchange_rates.py`, which uses only the blended rates. `api.frankfurter.dev/robots.txt`
  and `frankfurter.dev/robots.txt` are both `User-agent: *` / `Allow: /`, with no
  Content-Signal lines, and the site publishes an `llms.txt` for AI clients. No key:
  "There are no quotas. Requests are rate-limited to prevent abuse, but there are
  no monthly or daily caps." There is no terms page (`/terms` is 404); the docs say
  "Blended rates are Frankfurter's own calculation and free to use" and "Direct
  queries to individual provider endpoints remain subject to each provider's
  terms" (`/v2/providers` lists each source with a `terms_url`, often `null`). No
  attribution is required. The code is MIT-licensed and self-hostable with Docker.
  The ECB data API itself was ruled out on 2026-10-21 (its robots.txt blocks Claude
  agents and `python-requests`); Frankfurter collects the ECB's rates on its own
  servers, so a script using it doesn't fetch from the ECB. Full check in
  [`things-to-explore.md`](things-to-explore.md).
- **USGS earthquake catalog (ComCat)** ([API docs](https://earthquake.usgs.gov/fdsnws/event/1/)):
  checked 2026-10-27 before building an earthquakes script. Nothing is built on it
  yet. `earthquake.usgs.gov/robots.txt` is a 404, so nothing is disallowed and there
  is no Content-Signal line (RFC 9309 treats a missing file as allow-all). The API
  is documented and offered for programs ("GeoJSON is intended to be used as a
  programatic interface for applications"), needs no key, and answered a plain
  `python-requests` query (a 300 km circle around Tokyo) with JSON. It documents no
  rate limit, only a cap of 20,000 events per query (more is a 400). Terms: USGS
  information is generally public domain and "may be used without restriction";
  the only request is to credit the USGS ("(Product or data name) courtesy of the
  U.S. Geological Survey"), with an exception for non-USGS photos and graphics the
  USGS uses with permission, which the API doesn't serve. This comes from the USGS
  [crediting page](https://www.usgs.gov/information-policies-and-instructions/crediting-usgs)
  and [citation FAQ](https://www.usgs.gov/faqs/how-should-i-cite-a-usgs-website)
  as quoted in search results. `www.usgs.gov`, which holds the policy pages and its
  own robots.txt, answers automated fetches (curl and WebFetch) with a CloudFront
  403 or an empty page; a script wouldn't call that host, only `earthquake.usgs.gov`.
  The API page's "Feed Life Cycle Policy" link is a 404. Full check in
  [`things-to-explore.md`](things-to-explore.md).
