# Test suite

Unit tests for the scripts and helper modules at the repository root. Everything
runs **offline** — every network call is monkeypatched, so running the suite
never touches Yahoo Finance, Open-Meteo (weather or air quality), Hacker News,
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
  test_yahoo_finance.py
  test_indicators.py
  test_valuation.py
  test_doctests.py            – runs the indicators.py / valuation.py doctests
  test_weather.py
  test_weather_forecast.py
  test_air_quality.py
  test_hottest_tech_discussions.py
  test_market_top_volume.py
  test_stock_price_history.py
  test_stock_candlestick_chart.py
  test_stock_rebased_chart.py
  test_stock_tech_buzz_agent.py
  test_stock_intrinsic_value.py
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
| `test_cli_utils.py` | `cli_utils` | `positive_int` accept/reject; `require_env` set / missing / empty, plain vs JSON; `validate_url_scheme` accept (http/https) / reject (missing or other scheme) plain vs JSON; `die` plain vs JSON, exit code, stream; `load_dotenv` (missing file, populate, quoting, real-env precedence); `format_result`; `print_results` (JSON array, empty-list message, multi-row text output) |
| `test_yahoo_finance.py` | `yahoo_finance` | `parse_date`; `add_window_args` defaults and exit-2 rejections (range+last, unknown range, `--last 0`); `session_datetime` gmtoffset shift (both directions) and naive result; `fetch_crumb` cookie → crumb order, fallback to the next cookie page, crumb request error, unusable-crumb matrix (HTML, blank, too long, non-2xx); `crumb_session` headers + crumb; `build_params` window branches, priority order, look-back math, errors; `meta_summary`; `extract_series`; `fetch_history` payload/error handling and the actual `requests.get` call (URL, headers, timeout, params) |
| `test_indicators.py` | `indicators` | every transform + `trend` + `_ols_slope`; `moving_average_cross` tie ("equal"); MA-cross-flip "double flip" and "equal run" behavior; `trend` sign on an all-negative series; `rebase` out-of-range index; error paths |
| `test_valuation.py` | `valuation` | `_growth_path` branches (including negative years); reference values; `discounted_cash_flow` `net_debt`/`shares` equity bridge; `implied_growth_rate` round-trips `discounted_cash_flow`, monotonicity, out-of-range raises |
| `test_doctests.py` | `indicators`, `valuation` | keeps the in-module doctests running under pytest |
| `test_weather.py` | `weather` | `weather_description`, `format_place`, `place_fields`, `geocode`, `get_weather`, `parse_args`, `main` |
| `test_weather_forecast.py` | `weather_forecast` | `_valid_days`, `get_forecast` day-record assembly, `format_forecast` (incl. precipitation amount and chance columns), `main` |
| `test_air_quality.py` | `air_quality` | `us_aqi_category` band boundaries + `None`; `get_air_quality` record assembly + missing-`us_aqi` case; `format_air_quality`; `parse_args`; `main` (request error, not found, JSON/text output) |
| `test_hottest_tech_discussions.py` | `hottest_tech_discussions` | `discussion_url`/`posted_at`/`story_to_dict`; `fetch_story` error-swallowing; `get_hottest_tech_discussions` type filter / score sort / limit / candidate-pool slice / pool scales with limit (4×); `main` (incl. invalid `--limit` exits 2 before any fetch) |
| `test_market_top_volume.py` | `market_top_volume` | `METRICS`/`MARKETS` structural consistency; `quote_to_dict`; `format_quote` ordering; `get_movers` predefined vs region path, filters, sort; `fetch_region_quotes` crumb/error/success; `main` (invalid `--limit` exits 2 before any fetch, valid limit passed through) |
| `test_stock_price_history.py` | `stock_price_history` | `extract_rows` rounding / unsettled-bar skip / gmtoffset date shift / None-safety; `main` `--last` trim, JSON shape, adj-close column, fetch-error exit, invalid `--start` date exit |
| `test_stock_candlestick_chart.py` | `stock_candlestick_chart` | `_parse_ma_arg` / `_parse_flip_ma_arg` full matrices; `extract_rows` skips bars with missing OHLC, date is `datetime`; `main` invalid `--start` date exit |
| `test_stock_rebased_chart.py` | `stock_rebased_chart` | `fetch_closes` None-close skip; `main` base-date defaulting + fallback, per-symbol skip when the base date is missing, invalid `--base-date`, all-symbols-fail exit |
| `test_stock_tech_buzz_agent.py` | `stock_tech_buzz_agent` | `normalize_company_name` (one outer suffix); `stock_mentions_in_title` case-sensitivity / ambiguous symbols / word boundaries / short-name skip; `get_top_volume_stocks` dedup; `find_stock_buzz` match/no-match; `main` (text output with price / % change / comment count, malformed-payload `KeyError` exits 1 as JSON, invalid `--stock-limit` / `--discussion-limit` exits 2 before any fetch) |
| `test_stock_intrinsic_value.py` | `stock_intrinsic_value` | `_num` / `_text` raw-unwrap and type matrices; `_analyst_growth` by period; `collect_inputs` flattening plus price / shares / beta / name fallbacks and `net_debt` needing both debt and cash; `resolve_assumptions` CAPM + analyst-5y defaults, user overrides, no-beta / no-estimate defaults, 1y growth fallback, discount rate raised above terminal growth; `compute_estimates` every method against `valuation.py` (reverse DCF round-trips the price), user multiples, negative FCF / non-payer / loss-maker blanks, Graham cap and negative-growth skip, missing net debt as zero; `_vs_price` matrix; `build_json` shape; `build_report` sections and low-yield note; `fetch_fundamentals` cookie → crumb → host order with a `FakeSession`, host fall-through on an error body, HTML crumb ignored (crumbless attempts), all-fail raises last error, non-JSON status; `parse_args` defaults and exit-2 matrix; `main` (JSON/text output, upper-cased symbol, fetch error and no-price exit 1, invalid `--years` exits 2 before any fetch) |
| `test_web_search_brave.py` | `web_search_brave` | `strip_markup`; `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_results` pagination / early-stop / truncation / `raise_for_status`; `result_to_dict`; `parse_args`; `main` (missing key, request error, JSON/text output, no results) |
| `test_web_search_duckduckgo.py` | `web_search_duckduckgo` | `fetch_results` via a fake `DDGS` context manager, including `DDGSException` propagation; `result_to_dict`; `parse_args`; `main` (missing `ddgs` dependency, search error, JSON/text output, no results) |
| `test_web_search_exa.py` | `web_search_exa` | `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_results` single-request `numResults` capping / truncation / `raise_for_status` / missing `results` key; `result_to_dict` (including `null` text field); `parse_args`; `main` (missing key, request error, JSON/text output, no results) |
| `test_web_search_perplexity.py` | `web_search_perplexity` | `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_answer` (answer + sources, custom `--model`, missing `search_results`, `raise_for_status`, empty/missing `choices` or empty answer raises); `source_to_dict`; `format_answer` (with/without sources); `parse_args`; `main` (missing key, request error, JSON output with source-list trimming, text output) |
| `test_web_search_serpapi.py` | `web_search_serpapi` | `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_results` pagination / early-stop / truncation / `raise_for_status` / in-band `"error"` field / "no results" error treated as an empty result (first page or later page); `result_to_dict`; `parse_args`; `main` (missing key, request error, JSON/text output, no results) |
| `test_web_search_serper.py` | `web_search_serper` | `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_results` pagination / early-stop / truncation / `raise_for_status` / in-band `"message"` field; `result_to_dict`; `parse_args`; `main` (missing key, request error, JSON/text output, no results) |
| `test_web_search_tavily.py` | `web_search_tavily` | `load_dotenv` (missing file, populate, quoting, real-env precedence); `fetch_results` single-request `max_results` capping / truncation / `raise_for_status` / missing `results` key; `result_to_dict`; `parse_args`; `main` (missing key, request error, JSON/text output, no results) |
| `test_hottest_discussions_server.py` | `app/hottest_discussions/hottest_discussions_server` | `render_limit_options` default marker; `render_page` empty shell that calls `/api/discussions` and never Hacker News directly; `parse_limit` accept/reject matrix; `get_discussions` calls the script with the limit and shapes rows via `story_to_dict`; `HottestDiscussionsHandler` page / success / default limit 10 / invalid limit 400 / fetch error 502 / unknown path 404; `parse_args` defaults (port 8001), overrides, bad port exit 2 |
| `test_stock_info_server.py` | `app/stock_information/stock_info_server` | `normalize_symbol` accept/reject matrix; `get_stock_info` meta fields, gmtoffset dating, fallback to latest settled bar, previous-close/change (incl. an in-progress bar that already has a close, and no earlier bar), 52-week low/high present and absent, name fallback, no-price error; `get_valuation` runs the `stock_intrinsic_value` pipeline over canned fundamentals (all estimate keys, sector/industry, trailing P/E, dividend rate, undervalued/fair-value/overvalued summary, CAPM default rate, JSON-serializable), no-price error; `summarize_estimates` undervalued/fair-value/overvalued counting (exact-1% boundary, negative and missing values, custom threshold); `StockInfoHandler` page (incl. company/price/valuation elements) / quote and valuation 200 / invalid-or-missing symbol 400 / fetch error 502 / unknown path 404; `parse_args` defaults, overrides, bad port exit 2 |
| `test_url_availability.py` | `url_availability` | `check_url` 200/404/500 classification, timeout pass-through, connection-error propagation; `format_result` redirect line + available/not-available label; `parse_args`; `main` (missing scheme, request error, JSON/text output) |
| `test_url_content.py` | `url_content` | `is_text_content_type` accept/reject matrix incl. missing header; `extract_text` tag-stripping, script/style removal, whitespace collapsing, missing-`bs4` `ImportError`; `fetch_content` basic fetch, truncation, missing content-type, binary content-type raises, HTTP error raises, connection-error propagation, timeout pass-through, `--text` extraction + `text_extracted` flag; `format_result` redirect + truncated markers; `parse_args` incl. `--text`; `main` (missing scheme, request error, value error, missing-`bs4` error, `--text` pass-through, JSON/text output) |
| `test_url_links.py` | `url_links` | `extract_links` href/text pairing, relative-link resolution, absolute links kept as-is, skips anchors with no/empty `href`, whitespace collapsing, empty-text links, `mailto:`/`tel:`/`javascript:` links kept, document order, missing-`bs4` `ImportError`; `fetch_links` basic fetch, resolution against `final_url`, non-HTML/missing content-type raises, HTTP error raises, connection-error propagation, timeout pass-through, no-links case; `format_result` redirect line, link list, `(no text)` marker; `parse_args`; `main` (missing scheme, request error, value error, missing-`bs4` error, timeout pass-through, JSON/text output) |

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
