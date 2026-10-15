# URL Links

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use cli_utils.py's validate_url_scheme().
- Use BeautifulSoup (beautifulsoup4) to parse the page.

## Actions

- Run as python3 url_links.py from the repo root.
- Take:
    - {{URL}}: must start with http:// or https://; anything else is rejected before any request.
    - A request timeout in seconds (default: 10).
- Request the page, following redirects.
    - Fail on a 4xx or 5xx status.
    - Fail on non-HTML content.
    - If beautifulsoup4 isn't installed, fail with an error.
- Extract every link, in page order:
    - Make relative links absolute, against the final URL.
    - Skip links with an empty target; keep everything else, including mailto:, tel: and javascript: links, and repeats.
- Output:
    - {{URL}} {{Final URL}} {{Link Count}}
    - One entry per link: {{Link Text}} {{Link URL}}
    - With --json: {url, final_url, status_code, content_type, link_count, links: [{text, url}]}.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
