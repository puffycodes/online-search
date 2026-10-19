#!/usr/bin/env python3
"""
Serve a small local web page for the hottest technology discussions.

The page starts empty. A drop-down picks how many discussions to retrieve
(10/25/50, default 10), and clicking Refresh calls this server's
/api/discussions endpoint, which runs hottest_tech_discussions.py (at the
repository root) directly: get_hottest_tech_discussions() for the
ranking and story_to_dict() for each row, the same records that script
prints with --json.

A server is used (rather than a static page) so the page runs the
script itself instead of a JavaScript copy of its logic.

Usage:
    python3 hottest_discussions_server.py [--host HOST] [--port PORT]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# hottest_tech_discussions.py lives at the repository root, two levels up
# from this file (app/hottest_discussions/hottest_discussions_server.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402

import hottest_tech_discussions as hn  # noqa: E402

DEFAULT_HOST = "127.0.0.1"
# 8001 so it can run alongside app/stock_information (default 8000).
DEFAULT_PORT = 8001

# Choices for the page's "how many discussions to retrieve" drop-down.
# RESULTS_TO_SHOW (from hottest_tech_discussions.py) is the default of 10.
LIMIT_OPTIONS = (hn.RESULTS_TO_SHOW, 25, 50)

PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hottest Tech Discussions</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f6f6ef;
    --card-bg: #ffffff;
    --text: #1a1a1a;
    --muted: #6b6b6b;
    --accent: #ff6600;
    --border: #e5e5e0;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #121212;
      --card-bg: #1c1c1c;
      --text: #eaeaea;
      --muted: #9a9a9a;
      --border: #2c2c2c;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }
  header {
    background: var(--accent);
    padding: 1.5rem 1rem;
    text-align: center;
  }
  header h1 {
    margin: 0;
    color: #fff;
    font-size: 1.6rem;
  }
  header p {
    margin: 0.35rem 0 0;
    color: #fff4ea;
    font-size: 0.85rem;
  }
  .controls {
    margin-top: 0.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }
  .controls label {
    color: #fff4ea;
    font-size: 0.85rem;
  }
  #limit-select {
    padding: 0.35rem 0.6rem;
    border: 1px solid #fff;
    border-radius: 999px;
    background: transparent;
    color: #fff;
    font-size: 0.85rem;
    cursor: pointer;
  }
  #limit-select option {
    color: #1a1a1a;
    background: #fff;
  }
  #refresh-btn {
    padding: 0.4rem 1.1rem;
    border: 1px solid #fff;
    border-radius: 999px;
    background: transparent;
    color: #fff;
    font-size: 0.85rem;
    cursor: pointer;
  }
  #refresh-btn:hover {
    background: rgba(255, 255, 255, 0.15);
  }
  #refresh-btn:disabled {
    opacity: 0.6;
    cursor: default;
  }
  #refresh-status {
    margin: 0.5rem 0 0;
    color: #fff4ea;
    font-size: 0.75rem;
    min-height: 1em;
  }
  main {
    max-width: 720px;
    margin: 0 auto;
    padding: 1.25rem 1rem 3rem;
  }
  ol {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li.story {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.9rem 1rem;
    margin-bottom: 0.75rem;
    display: flex;
    gap: 0.75rem;
  }
  .rank {
    color: var(--muted);
    font-weight: 600;
    min-width: 1.75rem;
    text-align: right;
  }
  .story-body h2 {
    margin: 0 0 0.3rem;
    font-size: 1.05rem;
    line-height: 1.35;
  }
  .story-body h2 a {
    color: var(--text);
    text-decoration: none;
  }
  .story-body h2 a:hover {
    text-decoration: underline;
  }
  .meta {
    color: var(--muted);
    font-size: 0.85rem;
  }
  .meta a {
    color: var(--muted);
  }
  .empty {
    text-align: center;
    color: var(--muted);
    padding: 2rem 0;
  }
  footer {
    text-align: center;
    color: var(--muted);
    font-size: 0.75rem;
    padding-bottom: 2rem;
  }
</style>
</head>
<body>
<header>
  <h1>Hottest Tech Discussions</h1>
  <p>Top stories on Hacker News right now</p>
  <div class="controls">
    <label for="limit-select">Show</label>
    <select id="limit-select">
__LIMIT_OPTIONS__
    </select>
    <button id="refresh-btn" type="button">&#8635; Refresh</button>
  </div>
  <p id="refresh-status"></p>
</header>
<main>
  <div id="discussions">
  <p class="empty">No discussions loaded yet &mdash; click Refresh above to fetch the top discussions.</p>
  </div>
  <footer id="fetched-at">Source: Hacker News API, via hottest_tech_discussions.py</footer>
</main>
<script>
(function () {
  var button = document.getElementById("refresh-btn");
  var status = document.getElementById("refresh-status");
  var container = document.getElementById("discussions");
  var footer = document.getElementById("fetched-at");
  var limitSelect = document.getElementById("limit-select");

  function fetchJson(url) {
    return fetch(url).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.error || ("HTTP " + response.status));
        return body;
      });
    });
  }

  function newTabLink(href, text) {
    var a = document.createElement("a");
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = text;
    return a;
  }

  // One row of hottest_tech_discussions.story_to_dict().
  function buildStoryEl(row) {
    var li = document.createElement("li");
    li.className = "story";

    var rankSpan = document.createElement("span");
    rankSpan.className = "rank";
    rankSpan.textContent = row.rank;

    var body = document.createElement("div");
    body.className = "story-body";

    var h2 = document.createElement("h2");
    h2.appendChild(newTabLink(row.url, row.title));

    var meta = document.createElement("div");
    meta.className = "meta";
    meta.appendChild(document.createTextNode(
      row.score + " points · " + row.comments + " comments · posted " + row.posted + " · "
    ));
    meta.appendChild(newTabLink(row.discussion_url, "discuss on HN"));

    body.appendChild(h2);
    body.appendChild(meta);
    li.appendChild(rankSpan);
    li.appendChild(body);
    return li;
  }

  function renderStories(rows) {
    container.innerHTML = "";
    if (!rows.length) {
      var empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "No discussions found.";
      container.appendChild(empty);
      return;
    }
    var ol = document.createElement("ol");
    rows.forEach(function (row) {
      ol.appendChild(buildStoryEl(row));
    });
    container.appendChild(ol);
  }

  function refresh() {
    button.disabled = true;
    status.textContent = "Refreshing…";

    fetchJson("/api/discussions?limit=" + encodeURIComponent(limitSelect.value))
      .then(function (data) {
        renderStories(data.discussions);
        footer.textContent = "Fetched " + data.fetched_at +
          " · Source: Hacker News API, via hottest_tech_discussions.py";
        status.textContent = "Updated just now";
      })
      .catch(function (err) {
        status.textContent = "Refresh failed: " + err.message;
      })
      .finally(function () {
        button.disabled = false;
      });
  }

  button.addEventListener("click", refresh);
})();
</script>
</body>
</html>
"""


def render_limit_options(selected=hn.RESULTS_TO_SHOW):
    """Return the drop-down's <option> tags, with ``selected`` pre-selected."""
    return "\n".join(
        '      <option value="{n}"{sel}>{n}</option>'.format(
            n=n, sel=" selected" if n == selected else ""
        )
        for n in LIMIT_OPTIONS
    )


def render_page():
    """Return the page: an empty shell with the drop-down defaulting to 10."""
    return PAGE_HTML.replace("__LIMIT_OPTIONS__", render_limit_options())


def parse_limit(value):
    """Return ``value`` as an int from LIMIT_OPTIONS, or raise ValueError."""
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = None
    if limit not in LIMIT_OPTIONS:
        options = ", ".join(str(n) for n in LIMIT_OPTIONS)
        raise ValueError(f"limit must be one of {options}, got {value!r}")
    return limit


def get_discussions(limit):
    """Run hottest_tech_discussions.py's ranking and shape it for the page.

    Returns ``{limit, fetched_at, discussions}``, where ``discussions`` is
    the same list of ``story_to_dict()`` rows that script prints with
    --json, and ``fetched_at`` is the UTC time of the fetch. Raises
    requests.RequestException (or ValueError on a malformed response)
    when Hacker News can't be reached.
    """
    stories = hn.get_hottest_tech_discussions(limit=limit)
    return {
        "limit": limit,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "discussions": [hn.story_to_dict(rank, s) for rank, s in enumerate(stories, start=1)],
    }


class HottestDiscussionsHandler(BaseHTTPRequestHandler):
    """Serves the page at ``/`` and JSON at ``/api/discussions``."""

    def _send(self, status, body, content_type):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status, payload):
        self._send(status, json.dumps(payload), "application/json; charset=utf-8")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._send(HTTPStatus.OK, render_page(), "text/html; charset=utf-8")
            return
        if url.path != "/api/discussions":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        raw = parse_qs(url.query).get("limit", [str(hn.RESULTS_TO_SHOW)])[0]
        try:
            limit = parse_limit(raw)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        try:
            payload = get_discussions(limit)
        except (requests.RequestException, ValueError) as exc:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"error": f"failed to fetch discussions from Hacker News: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Serve a local web page showing the hottest tech discussions."
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help=f"Interface to bind (default: {DEFAULT_HOST})"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Port to listen on (default: {DEFAULT_PORT})"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), HottestDiscussionsHandler)
    print(f"Serving Hottest Tech Discussions at http://{args.host}:{args.port}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
