# URL Metadata

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use cli_utils.py's validate_url_scheme().
- Use BeautifulSoup (beautifulsoup4) to parse the page.

## Actions

- Run as python3 url_metadata.py from the repo root.
- Take:
    - {{URL}}: must start with http:// or https://; anything else is rejected before any request.
    - A request timeout in seconds (default: 10).
- Request the page, following redirects.
    - Fail on a 4xx or 5xx status.
    - Fail on non-HTML content.
    - If beautifulsoup4 isn't installed, fail with an error.
- Extract:
    - {{Title}}: the page's title, preferring the one in the head (an inline SVG can have its own); whitespace collapsed.
    - {{Description}}: the meta description.
    - {{Canonical URL}}: the canonical link, made absolute against the final URL.
    - {{OpenGraph Tags}}: every og:* meta tag, keyed by its name without the prefix (og:title → title).
    - {{Twitter Card Tags}}: every twitter:* meta tag, keyed the same way.
    - Meta tag names are matched case-insensitively, from either the property or the name attribute.
    - URL-valued tags (url, image, image:url, image:secure_url) are made absolute against the final URL.
    - A tag that appears more than once keeps its first value; a tag with empty content is skipped.
    - Anything the page doesn't declare is left empty.
- Output:
    - {{URL}} {{Final URL}} {{Status}}
    - {{Title}} {{Description}} {{Canonical URL}}, or "-" when missing.
    - The OpenGraph and Twitter card tags, one per line, or "none".
    - With --json: {url, final_url, status_code, content_type, title, description, canonical, open_graph, twitter}; a missing field is null, an empty tag group {}.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
