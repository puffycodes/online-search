# URL Content

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use cli_utils.py's validate_url_scheme(), and its response_text() to decode the page (when the server names no charset, use the detected encoding rather than ISO-8859-1, so UTF-8 pages aren't garbled).
- Use BeautifulSoup (beautifulsoup4) for text extraction.
- Use url_metadata.py's extract_metadata() to read the page title.
- Use robots.py's check() for the robots.txt check.

## Actions

- Run as python3 url_content.py from the repo root.
- Take:
    - {{URL}}: must start with http:// or https://; anything else is rejected before any request.
    - A request timeout in seconds (default: 10).
    - The maximum number of characters to return (default: 20,000).
    - Whether to extract readable text instead of returning the raw content (default: no).
    - Whether to respect the site's robots.txt (default: no). Agents pass it whenever they, not the user, chose the URL.
- When respecting robots.txt, check the page before requesting it, as the product token online-search-url-content:
    - Refuse it if a robots.txt rule disallows it (RFC 9309: the longest matching rule wins, Allow wins a tie), if the site opts out of AI input (Content-Signal: ai-input=no), or if robots.txt can't be read because of a server error or a failed connection. A missing robots.txt (4xx) allows everything.
    - A refusal fails with an error starting "blocked:" and the reason, without requesting the page.
    - If a redirect ends on a different page, check that page too; if it is refused, discard its content and fail with "blocked after redirect to {{Final URL}}: ...".
- Request the page, following redirects.
    - Fail on a 4xx or 5xx status.
    - Fail on non-text content (e.g. images, PDFs).
- When extracting text, remove scripts and styles, and join the rest into one run of text.
    - If beautifulsoup4 isn't installed, fail with an error.
    - For an HTML page (or one with no content type), also report its {{Title}}: the page's title, else its og:title, else none. From the same download, with no second request.
- Cut the content to the maximum length.
- Output:
    - {{URL}} {{Final URL}} {{Status Code}} {{Content Type}} {{Title}} (when there is one) {{Length}}
    - Whether the content was cut off.
    - {{Content}}
    - With --json: {url, final_url, status_code, content_type, title, length, truncated, text_extracted, content, robots_checked}; title is null without text extraction, for non-HTML content, or when the page has none.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
