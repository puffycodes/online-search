# Hottest Discussions

A small local web app for the top discussions on Hacker News, Lobsters or both. It runs [`hottest_tech_discussions.py`](../../hottest_tech_discussions.py) (at the repo root) directly: the page's Refresh button calls this server, which calls that script's `get_rows()` and returns the same rows the script prints with `--json`, one section per site.

See [`docs/features.md`](docs/features.md) for the feature spec this app implements.

## Features

- **"From" drop-down** — where to look: Hacker News (default), Lobsters, or All Sources (both). Refresh reads it each time it's clicked.
- **"Show" drop-down** — how many discussions to retrieve **per site**: 10 (default), 25 or 50. With All Sources, 10 means up to 10 from each site.
- **One section per site** — headed with the site's name, Hacker News first. The sites are never ranked against each other or merged into one list, because their scores aren't comparable (Lobsters is much smaller). A site that returns nothing says "No discussions found." in its section.
- **Discussion cards** — each card shows the rank within its site and the title on the first line, the title linking to the discussed article (or to the thread for posts with no external link, such as Ask HN or a Lobsters text post), then points, comment count, posted time (UTC) and a "discuss on HN" or "discuss on Lobsters" link. Lobsters cards also show their tags.
- **Refresh button** — calls `GET /api/discussions?limit=N&source=S` and renders the result in place.
- **Fetched time** — after a refresh, the footer shows when the discussions were fetched and from which site(s) (`Fetched YYYY-MM-DD HH:MM UTC · Source: Hacker News and Lobsters, …`).
- **Empty on start** — the page shows no discussions until Refresh is clicked; loading the page makes no call to either site.
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

Then open <http://127.0.0.1:8001/>, pick a site from **From** and a count from **Show** if you want something other than 10 from Hacker News, and click **Refresh**.

The JSON endpoint can also be called directly. `source` is `hn` (the default when it's left out), `lobsters` or `all`:

```bash
curl "http://127.0.0.1:8001/api/discussions?limit=10&source=all"
# {"limit": 10, "source": "all",
#  "sites": [{"id": "hn", "name": "Hacker News"}, {"id": "lobsters", "name": "Lobsters"}],
#  "fetched_at": "2026-10-19 08:04 UTC",
#  "discussions": [{"rank": 1, "title": ..., "score": ..., "comments": ..., "posted": ...,
#                   "url": ..., "discussion_url": ..., "tags": [], "source": "hn"}, ...,
#                  {"rank": 1, ..., "tags": ["meta", "vibecoding"], "source": "lobsters"}, ...]}
```

`discussions` is grouped by site in the order of `sites`, with `rank` restarting at 1 for each site; `sites` lists every site fetched, even one that returned no rows.

## How it works

1. **Serve the page** — `GET /` returns the page: header, **From** drop-down (`SOURCE_OPTIONS`, Hacker News pre-selected), **Show** drop-down (`LIMIT_OPTIONS = (10, 25, 50)`, 10 pre-selected), **Refresh** button, an empty discussions container and a footer.
2. **Refresh** — the page's inline script calls `GET /api/discussions?limit=<N>&source=<S>` on the same server.
3. **Run the script** — the handler validates `limit` (`parse_limit`; missing means 10) and `source` (`parse_source`; missing means `hn`), then `get_discussions` calls `hottest_tech_discussions.get_rows()` with that choice's sites. The script ranks each site on its own: for HN, details for the first `limit × 4` top stories, non-stories dropped, sorted by score; for Lobsters, front pages until there are `limit × 4` candidates, sorted by score. If any selected site fails, the script raises `SourceError` naming it, and nothing is returned for the others.
4. **Render** — the browser draws one section per entry in `sites`, with that site's rows as cards, and updates the footer with the fetch time and site names.

## File structure

| File | Purpose |
|---|---|
| `hottest_discussions_server.py` | The server and page — the only thing you run |
| `docs/features.md` | Feature spec this app implements |
| `README.md` | This documentation |

## API reference

- `LIMIT_OPTIONS` — The **Show** drop-down's choices, `(10, 25, 50)`, per site; the first entry (`RESULTS_TO_SHOW`, from `hottest_tech_discussions.py`) is the default.
- `SOURCE_OPTIONS` / `DEFAULT_SOURCE` — The **From** drop-down's choices, `{value: (label, the script's sources)}`: `hn` → Hacker News, `lobsters` → Lobsters, `all` → All Sources (`hn` and `lobsters`); the default is `hn`.
- `render_limit_options(selected=10)` / `render_source_options(selected="hn")` — Return a drop-down's `<option>` tags with `selected` pre-selected.
- `render_page()` — Returns the full HTML page (empty discussions area, drop-downs at Hacker News and 10).
- `parse_limit(value)` — Returns `value` as an int if it's one of `LIMIT_OPTIONS`; raises `ValueError` otherwise.
- `parse_source(value)` — Returns `value` if it's one of `SOURCE_OPTIONS`; raises `ValueError` otherwise.
- `get_discussions(limit, source="hn")` — Runs the script's ranking for that choice's sites and returns `{limit, source, sites, fetched_at, discussions}`: `sites` is `[{id, name}]` in the script's order, `discussions` the script's rows grouped by site, and `fetched_at` a `YYYY-MM-DD HH:MM UTC` string. Raises the script's `SourceError`, whose message names the site, when any selected site can't be fetched.
- `HottestDiscussionsHandler` — `BaseHTTPRequestHandler` serving `/` (page) and `/api/discussions` (JSON).
- `parse_args(argv=None)` — Parses `--host` and `--port`.
- `main(argv=None)` — Starts a `ThreadingHTTPServer` and serves until Ctrl+C.

## Tests

Covered offline by [`tests/test_hottest_discussions_server.py`](../../tests/test_hottest_discussions_server.py): both drop-downs' options and the page shell (empty on start, calls the API with both parameters, per-site link text and Lobsters tags, no direct calls to either site), `parse_limit` and `parse_source` accept/reject, `get_discussions` (Hacker News by default, Lobsters only, All Sources per site and grouped, an empty site keeps its section, a failed site raises naming it), the HTTP handler (page, success, defaults, 400 for a bad limit or source, 502 naming the site, 404) and `parse_args`. Run from the repo root with `python3 -m pytest`; see [`tests/README.md`](../../tests/README.md).

## Error handling

| Situation | HTTP status | Page shows |
|---|---|---|
| `limit` not 10, 25 or 50 | 400 | `Refresh failed: limit must be one of 10, 25, 50, got '...'` |
| `source` not `hn`, `lobsters` or `all` | 400 | `Refresh failed: source must be one of hn, lobsters, all, got '...'` |
| A selected site unreachable / malformed response | 502 | `Refresh failed: failed to fetch discussions from <Site>: <reason>`, with no discussions shown |
| Unknown path | 404 | — |

A refresh that fails because a site couldn't be fetched clears the list, so no partial results are shown; a 400 does the same. Individual HN stories that fail to fetch are skipped by the script rather than failing the whole refresh. Bad `--port` values are rejected by argparse (exit code 2).

## Notes / limitations

- Inherits the same "hottest" definition as [`hottest_tech_discussions.py`](../../README.md#hottest_tech_discussionspy): highest score among the first 4× N of each site's current front page, no tech-specific keyword filtering, and results are a live snapshot that will differ between clicks.
- The same story often appears on both sites, under the same or a different link; with All Sources it's listed in each site's section, never combined.
- There's no Lobsters tag filter on the page (the script's `--exclude-tag`), so Lobsters' posts about the site itself (tagged `meta`) are shown.
- Nothing appears until Refresh is clicked — there's no auto-refresh or polling.
- The "Show" drop-down (and the API) only accept 10/25/50.
- Needs the server running; opening the page as a file won't work. Choosing 50 fetches 200 HN stories' details (plus up to 8 Lobsters pages with All Sources), so it takes noticeably longer than 10.
- Binds to `127.0.0.1` by default. Passing `--host 0.0.0.0` exposes it on your network with no authentication.
