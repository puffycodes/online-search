# Test suite

Unit tests for the scripts and helper modules at the repository root. Everything
runs **offline** — every network call is monkeypatched, so running the suite
never touches Yahoo Finance, Open-Meteo, or Hacker News.

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
  test_hottest_tech_discussions.py
  test_market_top_volume.py
  test_stock_close_history.py
  test_stock_candlestick.py
  test_stock_rebased_chart.py
  test_stock_tech_buzz_agent.py
  test_generate_page.py
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
| `test_cli_utils.py` | `cli_utils` | `positive_int` accept/reject; `die` plain vs JSON, exit code, stream |
| `test_yahoo_finance.py` | `yahoo_finance` | `parse_date`; `build_params` window branches, priority order, look-back math, errors; `meta_summary`; `extract_series`; `fetch_history` payload/error handling |
| `test_indicators.py` | `indicators` | every transform + `trend` + `_ols_slope`; MA-cross-flip "double flip" and "equal run" behavior; error paths |
| `test_valuation.py` | `valuation` | `_growth_path` branches; reference values; `implied_growth_rate` round-trips `discounted_cash_flow`, monotonicity, out-of-range raises |
| `test_doctests.py` | `indicators`, `valuation` | keeps the in-module doctests running under pytest |
| `test_weather.py` | `weather` | `weather_description`, `format_place`, `geocode`, `get_weather`, `parse_args`, `main` |
| `test_weather_forecast.py` | `weather_forecast` | `_valid_days`, `get_forecast` day-record assembly, `format_forecast`, `main` |
| `test_hottest_tech_discussions.py` | `hottest_tech_discussions` | `discussion_url`/`posted_at`/`story_to_dict`; `fetch_story` error-swallowing; `get_hottest_tech_discussions` type filter / score sort / limit / candidate-pool slice; `main` |
| `test_market_top_volume.py` | `market_top_volume` | `METRICS`/`MARKETS` structural consistency; `quote_to_dict`; `format_quote` ordering; `get_movers` predefined vs region path, filters, sort; `fetch_region_quotes` crumb/error/success; `main` limit clamp |
| `test_stock_close_history.py` | `stock_close_history` | `extract_rows` rounding / unsettled-bar skip / gmtoffset date shift / None-safety; `main` `--last` trim, JSON shape, adj-close column, error exit |
| `test_stock_candlestick.py` | `stock_candlestick` | `_parse_ma_arg` / `_parse_flip_ma_arg` full matrices; `extract_rows` skips bars with missing OHLC, date is `datetime` |
| `test_stock_rebased_chart.py` | `stock_rebased_chart` | `fetch_closes` None-close skip; `main` base-date defaulting + fallback, per-symbol skip when the base date is missing, invalid `--base-date`, all-symbols-fail exit |
| `test_stock_tech_buzz_agent.py` | `stock_tech_buzz_agent` | `normalize_company_name` (one outer suffix); `stock_mentions_in_title` case-sensitivity / ambiguous symbols / word boundaries / short-name skip; `get_top_volume_stocks` dedup; `find_stock_buzz` match/no-match; `main` |
| `test_generate_page.py` | `app/hottest_discussions/generate_page` | `render_limit_options` selected marker; `render_page` shell/timestamp/brace-resolution/invalid-limit; `parse_args`; `main` writes file + creates parent dir |

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
