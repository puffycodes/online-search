# Hottest Discussions

A small local web app for the top Hacker News discussions. It runs [`hottest_tech_discussions.py`](../../hottest_tech_discussions.py) (at the repo root) directly: the page's Refresh button calls this server, which calls that script's `get_hottest_tech_discussions()` and `story_to_dict()` and returns the same rows the script prints with `--json`.

See [`docs/features.md`](docs/features.md) for the feature spec this app implements.

## Features

- **Top discussions area** — the main card list on the page, populated by clicking Refresh. Each card shows rank, linked title, points, comment count, posted time (UTC) and a "discuss on HN" link.
- **Refresh button** — calls `GET /api/discussions?limit=N` and renders the result in place.
- **"Show" drop-down** — how many discussions to retrieve: 10 (default), 25 or 50. Refresh reads it each time it's clicked.
- **Empty on start** — the page shows no discussions until Refresh is clicked; loading the page makes no Hacker News call.
- **`hottest_tech_discussions.py` as the source** — the ranking runs in that script, not in a copy of it, so the page and the CLI always agree.

## Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/) (used by `hottest_tech_discussions.py`)

```bash
pip install requests
```

No web framework — the server is the standard library's `http.server`, and the page is a single inline HTML/CSS/JS string.

## Usage

Run from anywhere; the repo root is resolved relative to the script.

```bash
python3 app/hottest_discussions/hottest_discussions_server.py [--host HOST] [--port PORT]
```

| Flag | Default | Description |
|---|---|---|
| `--host HOST` | `127.0.0.1` | Interface to bind (localhost only by default) |
| `--port PORT` | `8001` | Port to listen on (8001 so it can run alongside `app/stock_information/` on 8000) |

Example:

```bash
python3 app/hottest_discussions/hottest_discussions_server.py
# Serving Hottest Tech Discussions at http://127.0.0.1:8001/ (Ctrl+C to stop)
```

Then open <http://127.0.0.1:8001/>, pick a count from **Show** if you want more than 10, and click **Refresh**.

The JSON endpoint can also be called directly:

```bash
curl "http://127.0.0.1:8001/api/discussions?limit=10"
# {"limit": 10, "fetched_at": "2026-10-01 06:53 UTC",
#  "discussions": [{"rank": 1, "title": ..., "score": ..., "comments": ..., "posted": ...,
#                   "url": ..., "discussion_url": ...}, ...]}
```

## How it works

1. **Serve the page** — `GET /` returns the page: header, **Show** drop-down (`LIMIT_OPTIONS = (10, 25, 50)`, 10 pre-selected), **Refresh** button, an empty discussions container and a footer.
2. **Refresh** — the page's inline script calls `GET /api/discussions?limit=<N>` on the same server.
3. **Run the script** — the handler validates `limit` (`parse_limit`; a missing `limit` means 10), then `get_discussions` calls `hottest_tech_discussions.get_hottest_tech_discussions(limit)`: HN's `topstories.json`, details for the first `limit × CANDIDATE_POOL_FACTOR` (4×) stories fetched with 10 threads, non-stories dropped, sorted by score, top `limit` kept. Each story is flattened with `story_to_dict()`.
4. **Render** — the browser draws the rows as cards and updates the footer with the fetch time.

## File structure

| File | Purpose |
|---|---|
| `hottest_discussions_server.py` | The server and page — the only thing you run |
| `docs/features.md` | Feature spec this app implements |
| `README.md` | This documentation |

## API reference

- `LIMIT_OPTIONS` — The drop-down's choices, `(10, 25, 50)`; the first entry (`RESULTS_TO_SHOW`, from `hottest_tech_discussions.py`) is the default.
- `render_limit_options(selected=10)` — Returns the drop-down's `<option>` tags with `selected` pre-selected.
- `render_page()` — Returns the full HTML page (empty discussions area, drop-down at 10).
- `parse_limit(value)` — Returns `value` as an int if it's one of `LIMIT_OPTIONS`; raises `ValueError` otherwise.
- `get_discussions(limit)` — Runs the script's ranking and returns `{limit, fetched_at, discussions}`, where `discussions` is the list of `story_to_dict()` rows and `fetched_at` is a `YYYY-MM-DD HH:MM UTC` string. Raises `requests.RequestException` (or `ValueError` on a malformed response) when Hacker News can't be reached.
- `HottestDiscussionsHandler` — `BaseHTTPRequestHandler` serving `/` (page) and `/api/discussions` (JSON).
- `parse_args(argv=None)` — Parses `--host` and `--port`.
- `main(argv=None)` — Starts a `ThreadingHTTPServer` and serves until Ctrl+C.

## Tests

Covered offline by [`tests/test_hottest_discussions_server.py`](../../tests/test_hottest_discussions_server.py): the drop-down options and page shell (empty on start, calls the API, no direct Hacker News calls), `parse_limit` accept/reject, `get_discussions` (calls the script with the limit, shapes rows with `story_to_dict`), the HTTP handler (page, success, default limit, 400, 502, 404) and `parse_args`. Run from the repo root with `python3 -m pytest`; see [`tests/README.md`](../../tests/README.md).

## Error handling

| Situation | HTTP status | Page shows |
|---|---|---|
| `limit` not 10, 25 or 50 | 400 | `Refresh failed: limit must be one of 10, 25, 50, got '...'` |
| Hacker News unreachable / malformed response | 502 | `Refresh failed: failed to fetch discussions from Hacker News: <reason>` |
| Unknown path | 404 | — |

A failed Refresh leaves the current list (empty, or the last successful one) on screen. Individual stories that fail to fetch are skipped by the script rather than failing the whole refresh. Bad `--port` values are rejected by argparse (exit code 2).

## Notes / limitations

- Inherits the same "hottest" definition as [`hottest_tech_discussions.py`](../../README.md#hottest_tech_discussionspy): highest score among the first 4× N of HN's current top stories, no tech-specific keyword filtering, and results are a live snapshot that will differ between clicks.
- Nothing appears until Refresh is clicked — there's no auto-refresh or polling.
- The "Show" drop-down (and the API) only accept 10/25/50.
- Needs the server running; opening the page as a file won't work. Choosing 50 fetches 200 stories' details, so it takes noticeably longer than 10.
- Binds to `127.0.0.1` by default. Passing `--host 0.0.0.0` exposes it on your network with no authentication.
