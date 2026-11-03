# URL Feed

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use cli_utils.py's validate_url_scheme(), robots.py's check() and review(), and hn.py's clean_text() for summaries.
- Parse feeds with defusedxml (feeds are untrusted XML), and find a page's feed with BeautifulSoup (beautifulsoup4).
- Send its own User-Agent ("online-search-url-feed") and match the same name in robots.txt.

## Actions

- Run as python3 url_feed.py from the repo root.
- Take:
    - {{URL}}: a feed, or a page that links to its feed; must start with http:// or https://.
    - How many items to show (default: 10).
    - An optional date: only items published on or after it.
    - The longest summary per item, in characters (default: 300).
    - --respect-robots or --warn-robots (not both), as in url_content.py.
    - A request timeout in seconds (default: 10).
- Fetch the URL; refuse a body over 5 MB.
    - If it is an HTML page, find the first feed it advertises (<link rel="alternate"> with an RSS or Atom type) and fetch that. A page with none is an error; never scrape the page instead.
- With --respect-robots, check robots.txt for the URL and for a discovered feed before fetching each, and refuse one that is disallowed or opts out of AI input.
- Parse RSS 2.0, RSS 1.0 (RDF) and Atom into items: {{Title}}, {{Link}}, {{Published}}, {{Author}}, {{Summary}}.
    - Refuse unsafe XML (entity expansion, external entities) and report malformed XML.
    - Read RFC 822 and ISO 8601 dates into UTC; leave an unreadable date empty rather than guessing.
    - Turn HTML in summaries into plain text, cut to the chosen length.
- Show dated items newest first, then undated ones in feed order. With a date, drop older and undated items and count the undated ones.
- With --warn-robots, report what the feed's robots.txt asks: an AI-input opt-out, and a rule asking automated clients not to fetch it.
- Output:
    - Feed: {{Feed Title}} ({{Format}}), {{Feed URL}}, and the page it was found on when discovered.
    - Any robots.txt notes.
    - Showing {{Shown}} of {{Item Count}} item(s), newest first.
    - Per item: {{Title}}, {{Published}} and {{Author}}, {{Link}}, {{Summary}}.
    - With --json: {url, feed_url, discovered, format, title, site_url, item_count, undated_skipped, items: [{title, link, published, author, summary}], robots_checked, ai_input_warning, robots_disallow_note}.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
