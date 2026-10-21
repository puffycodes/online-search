# Test suite

Unit tests for the scripts and helper modules at the repository root. Everything
runs **offline** — every network call is monkeypatched, so running the suite
never touches Yahoo Finance, EODHD, Alpha Vantage, Open-Meteo (weather or air quality), Hacker News,
any of the web search APIs (Brave, Serper, Tavily, SerpApi, Exa, Perplexity,
DuckDuckGo), or the arbitrary URLs fetched by the `url_*.py` scripts.

## Running

```bash
pip install -r requirements-dev.txt   # pytest + requests
python3 -m pytest                     # from the repo root
```

Useful variants:

```bash
python3 -m pytest tests/test_valuation.py          # one module
python3 -m pytest -k "build_params"                # one topic across modules
python3 -m pytest -q --no-header                   # quieter
python3 -m pytest -x -vv                           # stop on first failure, verbose
```

`pytest.ini` (at the repo root) sets `testpaths = tests`, so a bare
`python3 -m pytest` collects only this directory.

## How imports work

The scripts under test are single files at the repo root, not an installed
package. Two `conftest.py` files make them importable:

| File | Role |
|---|---|
| `conftest.py` (repo root) | prepends the repo root to `sys.path` so `import yahoo_finance`, `import weather`, … resolve during collection |
| `tests/conftest.py` | holds shared fixtures (currently `chart_result`) |

`tests/` has no `__init__.py`, so pytest also puts `tests/` itself on
`sys.path` — that is why `from helpers import FakeResponse` works from any test
module.

## Layout

```
tests/
  README.md          – this file
  conftest.py        – shared fixtures
  helpers.py         – FakeResponse / FakeSession (not a test module)
  test_cli_utils.py
  test_robots.py
  test_yahoo_finance.py
  test_indicators.py
  test_valuation.py
  test_doctests.py            – runs the indicators.py / valuation.py doctests
  test_weather.py
  test_weather_forecast.py
  test_weather_history.py
  test_air_quality.py
  test_hottest_tech_discussions.py
  test_hn.py
  test_hn_search.py
  test_hn_thread.py
  test_market_top_volume.py
  test_stock_price_history.py
  test_price_source.py
  test_daily_prices.py
  test_eodhd_price_history.py
  test_alphavantage_price_history.py
  test_stock_candlestick_chart.py
  test_stock_rebased_chart.py
  test_stock_risk.py
  test_stock_tech_buzz_agent.py
  test_stock_intrinsic_value.py
  test_stock_fundamental.py
  test_stock_earnings_calendar.py
  test_stock_analyst_targets.py
  test_stock_holders.py
  test_osv_vulnerabilities.py
  test_web_search_brave.py
  test_web_search_duckduckgo.py
  test_web_search_exa.py
  test_web_search_perplexity.py
  test_web_search_serpapi.py
  test_web_search_serper.py
  test_web_search_tavily.py
  test_hottest_discussions_server.py
  test_stock_info_server.py
  test_url_availability.py
  test_url_content.py
  test_url_links.py
  test_url_broken_links.py
  test_url_metadata.py
```

## Test doubles

### `helpers.FakeResponse`

A minimal duck-type of `requests.Response`.

```python
FakeResponse(json_data={"chart": {"result": [...]}})   # .json() returns it
FakeResponse(json_data=None)                            # .json() raises ValueError (non-JSON body)
FakeResponse(text="crumb123")                           # for endpoints read via .text
FakeResponse(json_data=payload,
             raise_for_status=requests.HTTPError("500"))  # .raise_for_status() raises
FakeResponse(status_code=404, reason="Not Found", url="https://x/y")  # .status_code / .reason / .url
```

### `helpers.FakeSession`

Duck-type of `requests.Session` that records calls and returns queued
responses. `get_responses` / `post_responses` are consumed in order; a call
past the end returns `FakeResponse(json_data={})`.

```python
session = FakeSession(
    get_responses=[FakeResponse(json_data={}), FakeResponse(text="crumb123")],
    post_responses=[FakeResponse(json_data={"finance": {"result": [{"quotes": []}]}})],
)
market_top_volume.fetch_region_quotes(session, "gb", "dayvolume", "DESC")
assert session.post_calls[0][1]["params"] == {"crumb": "crumb123"}
```

### `chart_result` fixture

A well-formed Yahoo chart `result` dict (one element of `chart.result`): three
settled daily bars for 2024-01-01/02/03 UTC with an `adjclose` block. Used to
exercise `yahoo_finance.extract_series` and the per-script `extract_rows`.

## Conventions

- **No network.** Patch the seam closest to the boundary:
  - `monkeypatch.setattr(yf.requests, "get", ...)` for `yahoo_finance.fetch_history`
  - `monkeypatch.setattr(price_source, "fetch_history", ...)` in the four price scripts' tests, and `eodhd_price_history.fetch_eod` / `alphavantage_price_history.fetch_daily` in `test_price_source.py`
  - `monkeypatch.setattr(weather, "fetch_json", ...)` for the Open-Meteo helpers
  - `monkeypatch.setattr(hn, "fetch_story", ...)` / `fetch_json` for Hacker News
  - `monkeypatch.setattr(mod, "get_movers", ...)` etc. when testing an aggregator
    or `main()` that sits above the fetch layer
- **`main()` tests** drive the real `argparse` parser via `main([...])`, patch the
  data-fetch function, and assert on `capsys` output and `SystemExit.code`.
  - JSON error paths: `json.loads(capsys.readouterr().err) == {"error": ...}`
  - a rejected `--last 0` / `--years 0` exits **2** (argparse), a fetch failure
    exits **1** (`cli_utils.die`)
- **Floats**: compare with `pytest.approx`; reference figures for the valuation
  functions come from their own docstrings.
- **Parametrize** accept/reject matrices (`positive_int`, `_parse_ma_arg`,
  `_valid_days`, …) rather than writing one test per case.
- Test files mirror module names: `foo.py` → `tests/test_foo.py`. Group related
  cases in a `class Test<Thing>`.

## What each module's tests cover

| Test module | Under test | Focus |
|---|---|---|
| `test_cli_utils.py` | `cli_utils` | `positive_int` accept/reject; `non_negative_int` accept (incl. 0) / reject; `bounded_int` within range / above maximum / rejected like `positive_int`; `require_env` set / missing / empty, plain vs JSON; `validate_url_scheme` accept (http/https) / reject (missing or other scheme) plain vs JSON; `response_text` on real `requests.Response` objects (charset-less UTF-8 `text/html` decoded correctly where plain `.text` garbles it, declared charsets respected, missing `Content-Type`, duck-typed response without encoding attributes); `die` plain vs JSON, exit code, stream; `load_dotenv` (missing file, populate, quoting, real-env precedence); `format_result`; `print_results` (JSON array, empty-list message, multi-row text output); `use_utf8_output` (cp1252 streams switched to UTF-8 and CJK / symbols written, streams without `reconfigure` and reconfigure errors left alone) |
| `test_yahoo_finance.py` | `yahoo_finance` | `parse_date`; `add_window_args` defaults and exit-2 rejections (range+last, unknown range, `--last 0`); `session_datetime` gmtoffset shift (both directions) and naive result; `fetch_crumb` cookie → crumb order, fallback to the next cookie page, crumb request error, unusable-crumb matrix (HTML, blank, too long, non-2xx); `crumb_session` headers + crumb; `fetch_quote_summary` requests the given modules with the crumb, empty result raises; `summary_num` / `summary_text` raw-unwrap and type matrices; `build_params` window branches, priority order, look-back math, errors; `meta_summary`; `extract_series`; `fetch_history` payload/error handling and the actual `requests.get` call (URL, headers, timeout, params) |
| `test_indicators.py` | `indicators` | every transform + `trend` + `_ols_slope`; `moving_average_cross` tie ("equal"); MA-cross-flip "double flip" and "equal run" behavior; `trend` sign on an all-negative series; `rebase` out-of-range index; `returns` same-length/empty/zero-divisor; `volatility` per-session vs annualized, zero for flat and constant-growth series, up/down symmetry; `max_drawdown` peak/trough/recovery indices, largest-not-latest, earliest-on-tie, no-fall `None`s; `correlation` ±1, returns-not-prices, symmetry, `None` for a series with no variance; error paths |
| `test_valuation.py` | `valuation` | `_growth_path` branches (including negative years); reference values; `discounted_cash_flow` `net_debt`/`shares` equity bridge; `implied_growth_rate` round-trips `discounted_cash_flow`, monotonicity, out-of-range raises |
| `test_doctests.py` | `indicators`, `valuation` | keeps the in-module doctests running under pytest |
| `test_weather.py` | `weather` | `weather_description`, `format_place`, `place_fields`, `fetch_json` (JSON body, Open-Meteo `reason` surfaced on an error status, plain `raise_for_status` otherwise), `daily_value`, `sun_fields` (local clock times, hours, polar night / midnight sun placeholders dropped, missing series), `format_sun`, `format_daylight`, `geocode`, `get_weather`, `parse_args`, `main`; `main` JSON `attribution` field and text report ending with the Open-Meteo credit |
| `test_weather_forecast.py` | `weather_forecast` | `_valid_days`, `uv_category` WHO bands (half-up rounding at the edges, missing), `get_forecast` day-record assembly incl. UV and sun fields and missing series, `DAILY_FIELDS` requests them, `format_forecast` (precipitation amount and chance columns, UV-and-sun table, polar night and missing values), `main`; `main` JSON `attribution` field and text report ending with the Open-Meteo credit |
| `test_weather_history.py` | `weather_history` | `resolve_window` via `parse_args` (single date, range, end defaults to today, `--last N` ends yesterday, `--last 1` is yesterday, 1940-01-01 / today / 366-day edges allowed, exit-2 matrix: no date, `--end` alone, `--date` with `--start`, reversed, pre-1940, future, over 366 days, bad format, `--last` with `--date` / `--start` / `--end`, `--last` 0 / non-integer / 367); `get_history` day records (all fields, unit, not found, missing values); `fetch_daily_history` params; `summarize` (aggregates, single day, missing values left out, no data); `format_history` (range table and summary, single-day title, polar night and no-data note); `main` (request error and not-found exit 1, JSON output and arguments passed, text progress line, bad window exits 2 before any fetch); `main` JSON `attribution` field and text report ending with the Open-Meteo credit |
| `test_air_quality.py` | `air_quality` | `us_aqi_category` band boundaries + `None`; `get_air_quality` record assembly (incl. pollen fields) + missing-`us_aqi` case; every pollen field requested; `format_pollen` (all `None`/missing → not available, zeros still shown, plant order); `format_air_quality`; `parse_args`; `main` (request error, not found, JSON/text output); `main` JSON `attribution` field and text report ending with the Open-Meteo credit |
| `test_hottest_tech_discussions.py` | `hottest_tech_discussions` | `story_to_dict`; `get_hottest_tech_discussions` type filter / score sort / limit / candidate-pool slice / pool scales with limit (4×); `main` (incl. invalid `--limit` exits 2 before any fetch) |
| `test_hn.py` | `hn` | `fetch_json` (JSON body, params/timeout passed through, Algolia `message` surfaced, fallback to `raise_for_status`); `fetch_story` (official item URL, missing item, request and JSON errors → `None`); `parse_item_id` (ids, item links, rejects other input); `discussion_url`; `posted_at` (fixed and missing time); `clean_text` (empty, paragraphs/tags/entities, blank-line collapse, truncation, default and no limit) |
| `test_hn_search.py` | `hn_search` | `is_job_thread` title matrix (capitalisation, "Freelancers?", leading space, untitled "Who wants to be hired?", and look-alikes that aren't monthly threads) and `is_job_hit` for comments and stories; `build_params` (defaults incl. whole-word matching, `--type` tags, author and story tags, negative `-story_` tags for excluded threads, inclusive UTC date window, min points, limit); `search` (relevance vs date endpoint, story passed through, missing fields) and its job-thread loop with a scripted `fetch_json` (found threads excluded and the search re-run, exclusions accumulating over rounds, one request when clean, `MAX_JOB_ROUNDS` cap with leftovers dropped, an id-less job hit dropped and counted, job-thread stories excluded, `include_job_threads` and `--story` unfiltered); `hit_to_dict` (story, self-post, comment, `max_chars`, missing fields); `format_hit` (story, indented text, comment, no story); `parse_args` defaults, flags (incl. `--include-job-threads`), `--story` id/link implying comments, and exit-2 matrix (incl. bad `--story`, `--story` with another `--type` or `--min-points`); `main` (JSON/text output, `--max-chars`, no results, `--story` search text/JSON and empty-result hint, singular counts, `job_threads_skipped` in JSON and the "Left out N job threads" line (also with no results, absent when none), `--include-job-threads` passed through, request and non-JSON errors exit 1) |
| `test_hn_thread.py` | `hn_thread` | `fetch_tree` (30 s timeout, 404 → `None`, other errors raise); `count_comments` / `is_empty`; `ranked_children` (HN `kids` order, deleted leaves dropped, unknown ids last, oldest-first without `kids`); `fetch_kids` (failed fetch → `None`, empty item → `[]`); `select_comments` (`--top` / `--replies` / `--depth` limits, ranked order fetched only for shown comments with replies, full and partial fallback to oldest first); `comment_to_dict` / `thread_to_dict` (counts, `[deleted]`, truncation, comment root); `format_thread` (story report, numbering, trimmed-reply notes and singular wording, unranked note, comment root); `parse_args` defaults, flags and exit-2 matrix; `main` (JSON/text output, missing item and request errors exit 1) |
| `test_market_top_volume.py` | `market_top_volume` | `METRICS`/`MARKETS` structural consistency; `quote_to_dict`; `format_quote` ordering; `get_movers` predefined vs region path, filters, sort; `fetch_region_quotes` crumb/error/success; `main` (invalid `--limit` exits 2 before any fetch, valid limit passed through) |
| `test_stock_price_history.py` | `stock_price_history` | `extract_rows` rounding / unsettled-bar skip / gmtoffset date shift / None-safety; `main` `--last` trim, JSON shape (incl. `source` and `notes`), notes printed in the text report, adj-close column, fetch-error exit, invalid `--start` date exit |
| `test_price_source.py` | `price_source` | `route` matrix (US, share class, each tested suffix, `.NS`/`.BO` → Alpha Vantage, index, FX incl. `JPY=X`, crypto) and refusals (`.SI`, `.T`, `=F`, unknown suffix); `window` (explicit dates, `--last`, every `VALID_RANGES` keyword, unknown range); `aggregate` (daily unchanged, weekly and monthly OHLCV, missing values, unknown interval); `chart_result` round-trip through `extract_series` / `session_datetime` / `meta_summary`; `fetch_history` (EODHD dispatch with the free-plan out-of-window bar dropped and its note, `5d` keeps five, weekly aggregation, Alpha Vantage dispatch with the 100-session note and null `adj_close`, request spacing, provider error named and key redacted, not-found, missing key, unsupported ticker refused before any call) |
| `test_daily_prices.py` | `daily_prices` | `parse_date`; `add_window_args` defaults and `--last 0` exit 2; `resolve_window` (default days, `--last` look-back, end defaults to today, start beats last, single day, errors for `--end` alone / reversed / bad date); `price_row` rounding, numeric strings, int volume, missing values; `in_window` inclusive bounds; `print_table` title, summary line, adj-close column only when it differs, currency suffix |
| `test_eodhd_price_history.py` | `eodhd_price_history` | `fetch_eod` request (URL, params incl. key and window, timeout), 404 "Ticker Not Found." and non-list body raise; `extract_rows` sorting, rounding, close-less bar skipped, repeated `warning` collapsed to one note; `main` (JSON shape and `--last` trim, the free plan's out-of-window bar dropped with its note, text table, network error with the key redacted, missing key exits 1, bad date exits 1 before the key check, `--last 0` exits 2) |
| `test_alphavantage_price_history.py` | `alphavantage_price_history` | `fetch_daily` compact / full request, `Error Message` / `Information` / `Note` refusals, empty body, missing series, HTTP error; `extract_rows` string conversion, sorting, null `adj_close`, close-less bar skipped; `history_note` (window before the compact data, inside it, `--full`, short listing); `main` (JSON shape and `--last` trim, note in JSON, text table, refusal exits 1, network error with the key redacted, missing key exits 1, `--end` without `--start` exits 1) |
| `test_stock_candlestick_chart.py` | `stock_candlestick_chart` | `_parse_ma_arg` / `_parse_flip_ma_arg` full matrices; `extract_rows` skips bars with missing OHLC, date is `datetime`; `main` invalid `--start` date exit |
| `test_stock_rebased_chart.py` | `stock_rebased_chart` | `fetch_closes` None-close skip; `main` base-date defaulting + fallback, per-symbol skip when the base date is missing, invalid `--base-date`, all-symbols-fail exit, `--last 0` exits 2; `--benchmark` rebased and passed to the renderer separately, never sets the default base date, absent by default, fetch failure or no base-date close drops only the benchmark, a benchmark also listed as a symbol is fetched and drawn once, benchmark-only exits 2 before any fetch, benchmark data alone still exits 1; `render_chart` draws the benchmark dashed in `BENCHMARK_COLOR` with a `(benchmark)` label (skipped without matplotlib) |
| `test_stock_risk.py` | `stock_risk` | `extract_closes` adjusted-close preference, falls back to raw close for the whole series when any session lacks an adjusted one, unsettled-bar skip, gmtoffset date, empty result; `periods_per_year` 252 for weekdays vs 365 with a weekend session; `summarize` change / volatility / drawdown dates and prices / recovery date / high and distance from it, no-fall `None`s, too-short-for-volatility `None`, weekend series annualized over 365, symbol fallback; `pair_correlation` aligns on shared dates (an unshared outlier is ignored), too few or no shared sessions → `None`; `parse_args` defaults, repeats dropped case-insensitively, benchmark also listed is measured once, benchmark-only / no symbol / `--range` with `--last` exit 2; `load_symbol` fetch error, no rows and non-positive price as skip reasons, `--last` trim; `main` JSON shape and pair order, single symbol has no pairs, failed symbol or benchmark skipped, all-fail and benchmark-only data exit 1, text report (progress line, benchmark label, worst fall, pairs, closing caveat, stderr warning, no-fall line), `--last 0` exits 2, invalid date exits 1 |
| `test_stock_tech_buzz_agent.py` | `stock_tech_buzz_agent` | `normalize_company_name` (one outer suffix); `stock_mentions_in_title` case-sensitivity / ambiguous symbols / word boundaries / short-name skip; `get_top_volume_stocks` dedup; `find_stock_buzz` match/no-match; `main` (text output with price / % change / comment count, malformed-payload `KeyError` exits 1 as JSON, invalid `--stock-limit` / `--discussion-limit` exits 2 before any fetch) |
| `test_stock_intrinsic_value.py` | `stock_intrinsic_value` | `_num` / `_text` raw-unwrap and type matrices; `_analyst_growth` by period; `collect_inputs` flattening plus price / shares / beta / name fallbacks, `net_debt` needing both debt and cash, and `dividend_rate` as yield × price (in the quote's minor unit for `GBp`, ignoring `dividendRate`; zero or missing yield → `None`); `resolve_assumptions` CAPM + analyst-5y defaults, user overrides, no-beta / no-estimate defaults, 1y growth fallback, discount rate raised above terminal growth; `compute_estimates` every method against `valuation.py` (reverse DCF round-trips the price), user multiples, negative FCF / non-payer / loss-maker blanks, Graham cap and negative-growth skip, missing net debt as zero; `_vs_price` matrix; `build_json` shape; `build_report` sections and low-yield note; `fetch_fundamentals` cookie → crumb → host order with a `FakeSession`, host fall-through on an error body, HTML crumb ignored (crumbless attempts), all-fail raises last error, non-JSON status; `parse_args` defaults and exit-2 matrix; `main` (JSON/text output, upper-cased symbol, fetch error and no-price exit 1, invalid `--years` exits 2 before any fetch) |
| `test_stock_fundamental.py` | `stock_fundamental` | `_ratio` matrix (negative numerator, missing / zero / negative denominator); `extract_indicators` read and derived indicators (PEG, FCF yield, debt/equity percent → ratio, net debt/EBITDA, cash conversion, dividend yield), every `INDICATOR_GROUPS` key extracted, missing fields → `None`, not-meaningful ratios (negative EBITDA, net income, growth) → `None`, zero gross margin → `None`, net cash → negative net debt/EBITDA; `build_json` shape; `build_report` groups, labels, formats and `-` for missing; `parse_args` defaults and missing-symbol exit 2; `main` (JSON/text output, upper-cased symbol, fetch error and no-price exit 1, unknown flag exits 2 before any fetch) |
| `test_stock_earnings_calendar.py` | `stock_earnings_calendar` | `next_earnings` confirmed date (UTC time, estimates), two timestamps as an estimated window, past/upcoming status, missing estimates and missing dates; `dividend_dates` dates, statuses and last amount, today counts as upcoming, no amount currency for minor-unit listings, no dividend → `None`; `earnings_history` oldest-first sort, report date and fiscal quarter matched from the `earnings` chart, unmatched quarter, rows without EPS dropped; `extract_calendar` reporting-currency fallbacks and a reporting currency that differs from trading; `build_report` sections, estimated window, missing sections, sub-unit dividend precision; `parse_args` defaults and missing-symbol exit 2; `main` (JSON/text output, modules requested, upper-cased symbol, fetch error and no-earnings exit 1, unknown flag exits 2 before any fetch) |
| `test_stock_analyst_targets.py` | `stock_analyst_targets` | `extract_targets` targets, upside and consensus, price fallback, no price → no upside, `none` key dropped; `recommendation_trend` newest-first sort with totals, empty months dropped; `analyst_actions` `--days` window with a fixed clock, newest-first sort, action/target-verb mapping, zero targets and blank grades → `None`, unknown codes passed through, undated entries skipped, missing module; `action_summary` counts; `has_coverage` covered / index / trend-only / actions-only; `build_report` sections, readable `STRONG BUY`, missing consensus and trend, actions table (`from -> to` only on a change), no-actions line; `parse_args` defaults, missing-symbol and bad `--days` exit 2; `main` (JSON/text output, modules requested, `--days` narrows the actions, upper-cased symbol, fetch error and no-coverage exit 1, unknown flag exits 2 before any fetch) |
| `test_stock_holders.py` | `stock_holders` | `classify` by description (sale/sold, purchase/bought, buy back, option exercise, award, gift, other), description winning over a missing role, blank-description buyback by the company (two-word name match), holder disclosure without a role, unspecified with one; `is_us_listing` suffix rule; `_price_range` single price, low-high range, thousands separator, 0 and missing → `None`; `insider_transactions` `--days` window with a fixed clock, newest-first sort, fields incl. direct/indirect and Yahoo's 0 placeholders → `None`, undated entries skipped, missing module; `insider_summary` sales and purchases totalled with other kinds only counted, `by_insider` most value first with ties broken by shares, a missing role filled from a later row, unnamed rows and non-trades left out; `extract_holders` US listing (ownership, funds, institutions) vs non-US (institutions `None`), `transaction_currency` (quote currency for US listings, `USD` for non-US, `None` with no price); `--trades-only` trimming the list but not the summary, keeping option exercises; `has_data` covered / ETF / funds-only / only buybacks left out by `--trades-only`; `build_report` sections, spelled-out other kinds, by-insider section and its cap, `--trades-only` note and empty-trades line, price range, non-US notes and hidden institutions, empty transactions and holders; `parse_args` defaults, `--trades-only` and exit-2 matrix; `main` (JSON/text output, modules requested, `--days`, `--trades-only` JSON, upper-cased symbol, fetch error and no-data exit 1, unknown flag exits 2 before any fetch) |
| `test_osv_vulnerabilities.py` | `osv_vulnerabilities` | `canonical_ecosystem` case-insensitive names, aliases (pip, cargo, golang, …), release suffix kept, unknown passed through; `source_name` known prefixes and unknown-prefix fallback; `post_query` JSON body and timeout, OSV `message` surfaced on an error status, non-JSON error falls back to the status; `fetch_vulns` payload with and without a version, empty body, `next_page_token` followed, page cap marks incomplete; `group_vulns` mutual, one-way, transitive and shared-CVE merges, unrelated non-CVE alias not merged; `fixed_versions` ECOSYSTEM ranges, de-duplication, PyPI name normalization, other packages and GIT ranges ignored, release suffix ignored for the match; `summarize_group` GHSA preferred, every field, summary-from-details fallback, details clipped, unrated, malicious flag, earliest published; `build_results` order (malicious, severity, newest), withdrawn records dropped; `parse_args` defaults, required ecosystem, bad `--limit` and blank package exit 2; `main` JSON shape, `--limit` cuts the list not the count, text report (progress line, header, labels, fixed / no fix, sources, links, attribution last), more-results and incomplete notes, `[MALICIOUS]`, no-results spelling warning (text and JSON), fetch error exits 1 (JSON and text), missing ecosystem exits 2 before any fetch |
| `test_web_search_brave.py` | `web_search_brave` | `strip_markup`; `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_results` pagination / early-stop / truncation / `raise_for_status`; `result_to_dict`; `parse_args`; `main` (missing key, request error, JSON/text output, no results) |
| `test_web_search_duckduckgo.py` | `web_search_duckduckgo` | `fetch_results` via a fake `DDGS` context manager, including `DDGSException` propagation; `result_to_dict`; `parse_args`; `main` (missing `ddgs` dependency, search error, JSON/text output, no results); `fetch_results` pins the backend to DuckDuckGo (never ddgs's `auto` metasearch) |
| `test_web_search_exa.py` | `web_search_exa` | `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_results` single-request `numResults` capping / truncation / `raise_for_status` / missing `results` key; `result_to_dict` (including `null` text field); `parse_args`; `main` (missing key, request error, JSON/text output, no results) |
| `test_web_search_perplexity.py` | `web_search_perplexity` | `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_answer` (answer + sources, custom `--model`, missing `search_results`, `raise_for_status`, empty/missing `choices` or empty answer raises); `source_to_dict`; `format_answer` (with/without sources); `parse_args`; `main` (missing key, request error, JSON output with source-list trimming, text output) |
| `test_web_search_serpapi.py` | `web_search_serpapi` | `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_results` pagination / early-stop / truncation / `raise_for_status` / in-band `"error"` field / "no results" error treated as an empty result (first page or later page); `result_to_dict`; `parse_args`; `main` (missing key, request error, JSON/text output, no results) |
| `test_web_search_serper.py` | `web_search_serper` | `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_results` pagination / early-stop / truncation / `raise_for_status` / in-band `"message"` field; `result_to_dict`; `parse_args`; `main` (missing key, request error, JSON/text output, no results) |
| `test_web_search_tavily.py` | `web_search_tavily` | `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_results` single-request `max_results` capping / truncation / `raise_for_status` / missing `results` key; `result_to_dict`; `parse_args`; `main` (missing key, request error, JSON/text output, no results) |
| `test_hottest_discussions_server.py` | `app/hottest_discussions/hottest_discussions_server` | `render_limit_options` default marker; `render_page` empty shell that calls `/api/discussions` and never Hacker News directly; `parse_limit` accept/reject matrix; `get_discussions` calls the script with the limit and shapes rows via `story_to_dict`; `HottestDiscussionsHandler` page / success / default limit 10 / invalid limit 400 / fetch error 502 / unknown path 404; `parse_args` defaults (port 8001), overrides, bad port exit 2 |
| `test_stock_info_server.py` | `app/stock_information/stock_info_server` | `normalize_symbol` accept/reject matrix; `get_stock_info` meta fields, gmtoffset dating, fallback to latest settled bar, previous-close/change (incl. an in-progress bar that already has a close, and no earlier bar), 52-week low/high present and absent, name fallback, no-price error; `get_valuation` runs the `stock_intrinsic_value` pipeline over canned fundamentals (all estimate keys, sector/industry, trailing P/E, dividend rate, undervalued/fair-value/overvalued summary, CAPM default rate, `indicators` present, JSON-serializable), no-price error; `summarize_estimates` undervalued/fair-value/overvalued counting (exact-1% boundary, negative and missing values, custom threshold); `StockInfoHandler` page (incl. company/price/fundamentals/valuation elements) / quote and valuation 200 / invalid-or-missing symbol 400 / fetch error 502 / unknown path 404; `parse_args` defaults, overrides, bad port exit 2 |
| `test_url_availability.py` | `url_availability` | `check_url` 200/404/500 classification, timeout pass-through, connection-error propagation; `fetch_wayback` (snapshot found + ISO date, none, snapshot marked unavailable, odd timestamp/status kept raw, 429 and non-JSON raise); `add_wayback` (snapshot added, failures recorded in `archive_error`); `unreachable_result` shape; `format_result` redirect line, available/not-available label, `NOT REACHABLE`, archived-copy / none-found / lookup-failed lines; `parse_args` (incl. `--wayback`); `main` (missing scheme, request error, JSON/text output; with `--wayback`: dead page looked up with the `--timeout`, available page and no-flag runs never looked up, connection error reported with exit 0, failed lookup still reported) |
| `test_robots.py` | `robots` | `parse` groups (shared User-agent lines), comments, case, empty `Disallow`, unknown lines, a `Content-Signal` kept in its own group (Lobsters' layout) or global before any group; `parse_signal` pairs, path scope, junk; `is_allowed` no rules, `Disallow: /`, longest match beats first match (`Allow: /` then `Disallow: /search`), a more specific `Allow`, `Allow` wins a tie, `*` and `$` wildcards, a named group replacing `*`, another bot's group ignored, `/robots.txt` always allowed; `ai_input_allowed` no signal, `*`-group and global opt-outs, other signals and other groups ignored, a path-scoped signal overriding an unscoped one; `url_path` / `robots_url`; `fetch` text with the caller's User-Agent and timeout, 500 KiB cap, `4xx` allows everything, `5xx` and connection errors are problems; `check` allowed, no file, disallowed, AI opt-out and unreadable reasons; `review` AI opt-out and disallow reasons, both, neither, unreadable robots.txt gives no notes, Lobsters' layout gets only the disallow note |
| `test_url_content.py` | `url_content` | `is_text_content_type` accept/reject matrix incl. missing header; `extract_text` tag-stripping, script/style removal, whitespace collapsing, missing-`bs4` `ImportError`; `fetch_content` basic fetch, truncation, missing content-type, binary content-type raises, HTTP error raises, connection-error propagation, timeout pass-through, `--text` extraction + `text_extracted` flag; `page_title` from `<title>`, `og:title` fallback, neither → `None`; `--text` title reported (also with no content type), `None` without `--text` and for non-HTML; `format_result` redirect + truncated markers and `Title:` line only when there is a title; `parse_args` incl. `--text`; `main` (missing scheme, request error, value error, missing-`bs4` error, `--text` pass-through, JSON/text output); `--respect-robots` (off by default with `robots_checked: false`, an allowed page fetched with `robots_checked: true`, a refused page never fetched and exits 1 with `blocked:` in JSON and text, a redirect target checked again and its content discarded when refused, a fragment-only difference not rechecked, the script's User-Agent and product token passed to `robots.check`); `--warn-robots` (exclusive with `--respect-robots`, exit 2; `ai_input_warning` and `robots_disallow_note` reported with the page still returned and never the refusing check; both `null` without notes; checks the page after redirects; not run without the flag; `Warning:` and `Note:` lines in the text report; both `null` under `--respect-robots`; the script's User-Agent and product token passed to `robots.review`) |
| `test_url_broken_links.py` | `url_broken_links` | `non_negative_float`; `HostThrottle` spacing per host; `RobotsCache` one fetch per host through the throttle with this script's User-Agent, problem kept; `select_links` (non-web, fragments, same page, duplicates, `--scope`, cap in page order); `classify` matrix (ok / redirected / broken / blocked 401-403-429); `lands_on_home_page` matrix; `check_link` (ok with its own User-Agent, home-page redirect note, broken, connection error, robots.txt disallow skips the fetch, unreadable robots.txt: connection failure unreachable, other failures skipped); `add_wayback_copies` (dead links only, stops at the first 429); `page_notes` (AI opt-out and disallow, unreadable robots.txt); `check_page` counts and Wayback; `format_result` sections; `main` (JSON, progress line, page failure and missing bs4 exit 1, bad scheme exit 1, bad options exit 2) |
| `test_url_links.py` | `url_links` | `extract_links` href/text pairing, relative-link resolution, absolute links kept as-is, skips anchors with no/empty `href`, whitespace collapsing, empty-text links, `mailto:`/`tel:`/`javascript:` links kept, document order, missing-`bs4` `ImportError`; `fetch_links` basic fetch, resolution against `final_url`, non-HTML/missing content-type raises, HTTP error raises, connection-error propagation, timeout pass-through, no-links case; `format_result` redirect line, link list, `(no text)` marker; `parse_args`; `main` (missing scheme, request error, value error, missing-`bs4` error, timeout pass-through, JSON/text output) |
| `test_url_metadata.py` | `url_metadata` | `extract_metadata` full page (title, description, canonical, OpenGraph and Twitter groups), empty page, `<head>` title preferred over an `<svg>` title, title without `<head>`, blank title → `None`, meta names case-insensitive from `property` or `name`, first value wins, empty content skipped, only URL-valued tags resolved, canonical among several `rel` values, empty canonical `href` ignored, unrelated meta ignored, missing-`bs4` `ImportError`; `fetch_metadata` basic fetch (timeout, redirects, `User-Agent`), resolution against `final_url`, non-HTML/missing content-type raises, HTTP error raises, connection-error propagation, timeout pass-through; `format_result` full report, redirect line, `-` / `none` for missing fields; `parse_args`; `main` (missing scheme, request error, value error, missing-`bs4` error, timeout pass-through, JSON/text output) |

## Adding a test

1. Find (or add) `tests/test_<module>.py`.
2. Add a `class Test<Thing>` and a focused method per behavior.
3. If the code path makes an HTTP call, patch the nearest seam (see
   **Conventions**); reuse `FakeResponse` / `FakeSession` from `helpers`.
4. Run `python3 -m pytest tests/test_<module>.py -q`.

## Not covered here (see the repo root README's plan)

Chart rendering (`render_chart` in the two matplotlib scripts) and live
end-to-end calls are out of scope for this suite — they belong to the Tier 3 /
Tier 4 buckets described when the suite was scoped.
