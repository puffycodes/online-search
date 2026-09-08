# Hottest Discussions

A small static-site generator that pairs with [`hottest_tech_discussions.py`](../../hottest_tech_discussions.py) (at the repo root) to produce a browsable web page for the top Hacker News discussions — an HTML file you can open locally or host anywhere.

See [`docs/features.md`](docs/features.md) for the one-line feature list this app was built against.

## Features

- **Top discussions area** — the main card list on the page, populated by clicking Refresh.
- **Refresh button** — fetches and renders the list client-side, in place, without regenerating the file (see [How it works](#how-it-works)).
- **"Show" drop-down** — lets the visitor pick how many discussions to retrieve: 10 (default), 25, or 50. Refresh reads this value each time it's clicked.
- **Empty on start** — the generated page shows no discussions until Refresh is clicked; `generate_page.py` does not fetch anything at generation time.
- **`hottest_tech_discussions.py` as the source of truth** — the Refresh button (JavaScript, in the browser) retrieves stories from the same Hacker News endpoints and ranking logic as that script.

## Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/) (used by `hottest_tech_discussions.py`)

```bash
pip install requests
```

No other dependencies — the page is rendered with plain string templates, no Jinja/Flask/Node involved. `generate_page.py` doesn't call the network itself; `requests` is only pulled in transitively because it imports a constant from `hottest_tech_discussions.py`.

## Usage

Run from anywhere; paths are resolved relative to this file, not your working directory.

```bash
python3 app/hottest_discussions/generate_page.py [--limit {10,25,50}] [--output PATH]
```

| Flag | Default | Description |
|---|---|---|
| `--limit {10,25,50}` | 10 | Which option the page's "Show" drop-down starts pre-selected to |
| `--output PATH` | `app/hottest_discussions/index.html` | Where to write the generated HTML file |

`--limit` only sets the drop-down's *initial* selection — the visitor can change it in the browser at any time before clicking Refresh, and only 10/25/50 are offered.

Example:

```bash
python3 app/hottest_discussions/generate_page.py --limit 25
# Wrote empty page shell to .../app/hottest_discussions/index.html
# Open it in a browser and click Refresh to load discussions.
```

Then open `app/hottest_discussions/index.html` in a browser. It loads instantly with no discussions shown — pick a count from the **Show** drop-down (10/25/50) if you want something other than the pre-selected default, then click **Refresh** to fetch and render that many stories in place. There's no server involved at any point; it's a self-contained file (inline CSS/JS) that only talks to the network when you click Refresh.

## How it works

1. **Generate the shell** — `generate_page.py` renders `PAGE_TEMPLATE` — header, **Show** drop-down (options from `LIMIT_OPTIONS = (10, 25, 50)`, pre-selected per `--limit`), **Refresh** button, an empty `#discussions` container, and a "Generated `<UTC timestamp>`" footer — with no network call and no discussions embedded.
2. **Write file** — The finished HTML string is written to `--output` (creating parent directories if needed).
3. **Refresh in the browser** — Clicking **Refresh** reads the current drop-down value and runs an inline `<script>` that mirrors `hottest_tech_discussions.py`'s `get_hottest_tech_discussions` logic in JavaScript: it calls the same Hacker News Firebase endpoints (`/v0/topstories.json`, then `/v0/item/{id}.json` for a candidate pool 4x the selected count), filters to `type === "story"`, sorts by score, and renders the top N as cards (rank, linked title, points, comment count, posted time, discussion link) directly into `#discussions` — no server or Python process involved. It also updates the footer's "Generated" timestamp to when the data was fetched.

## File structure

| File | Purpose |
|---|---|
| `generate_page.py` | The generator script — the only thing you run |
| `index.html` | Generated output (gitignored churn candidate — regenerate anytime; not hand-edited) |
| `docs/features.md` | Feature spec this app implements |
| `README.md` | This documentation |

## Styling

The page is a single HTML file with inline `<style>` — an HN-style card list, `max-width: 720px` centered column, and `prefers-color-scheme`-based light/dark theming (no toggle, follows the OS/browser setting). A small inline `<script>` powers the Refresh button (see below); there's no other JavaScript and no build step.

## API reference

- `LIMIT_OPTIONS` — The drop-down's choices, `(10, 25, 50)`; the first entry (`RESULTS_TO_SHOW`, imported from `hottest_tech_discussions.py`) is the default.
- `render_limit_options(selected)` — Returns the `<option>` tags for the drop-down, marking `selected` as the pre-selected one.
- `render_page(limit=RESULTS_TO_SHOW)` — Returns the full HTML document as a string: the page shell with no discussions embedded, and the "Show" drop-down pre-selected to `limit`. Raises `ValueError` if `limit` isn't one of `LIMIT_OPTIONS`.
- `parse_args(argv=None)` — Parses `--limit` (restricted to `LIMIT_OPTIONS`) and `--output`.
- `main(argv=None)` — Entry point: renders the page shell, writes it to disk, and prints a one-line summary.

## Error handling

`generate_page.py` makes no network calls, so generation itself can't fail on a network error.

In the browser, a failed Refresh (network error, HN API down) leaves the current state (empty, or the last successfully loaded list) untouched and shows "Refresh failed: `<message>`" under the button instead. See [`hottest_tech_discussions.py`'s own error handling](../../README.md#error-handling) for how the CLI script (which uses the same endpoints) handles fetch failures.

## Notes / limitations

- Inherits the same "hottest" definition as [`hottest_tech_discussions.py`](../../README.md#hottest_tech_discussionspy): highest score among HN's current top stories, no tech-specific keyword filtering, and results are a live snapshot that will differ between clicks.
- The page never auto-loads or auto-refreshes discussions — nothing appears until Refresh is clicked, and there's no polling/interval or cron/scheduler wired up in this repo.
- The "Show" drop-down only offers 10/25/50; there's no free-text option, in the browser or via `--limit`.
- Static output only — no backend, no API endpoint, nothing to deploy beyond the HTML file itself. The Refresh button calls the public Hacker News Firebase API directly from the visitor's browser (same endpoints `hottest_tech_discussions.py` uses), so it needs outbound network access but no server of its own.
