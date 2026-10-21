# URL Broken Links

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use url_links.py's fetch_links() to get the page's links, url_availability.py's check_url() to check each one and add_wayback() for archived copies, and robots.py's fetch(), parse(), is_allowed(), ai_input_allowed() and url_path() for robots.txt.
- Use cli_utils.py's validate_url_scheme(), bounded_int(), positive_int() and die().
- Send its own User-Agent ("online-search-url-broken-links") on every request, and match the same name in robots.txt.

## Actions

- Run as python3 url_broken_links.py from the repo root.
- Take:
    - {{URL}}: the page whose links to check; must start with http:// or https://, anything else is rejected before any request.
    - At most how many links to check (default: 100, at most 1000).
    - The minimum gap between requests to the same host, in seconds (default: 1.0).
    - Which links to check: all (default), only internal ones (the page's own host), or only external ones.
    - An optional --wayback flag (off by default).
    - A request timeout in seconds (default: 10).
- Fetch the page (it's the user's choice, so regardless of its robots.txt) and extract its links.
- Choose the links to check, in page order:
    - Only http:// and https:// links; drop the #fragment; skip links back to the page itself and repeats.
    - Apply the internal / external choice, then the cap.
    - Count every link left out, by reason.
- Be polite while checking:
    - Space requests to the same host by the chosen gap.
    - Read each linked host's robots.txt once; don't fetch a link it disallows. An unreadable robots.txt counts as a full disallow, except that a host that can't be connected to at all (DNS failure, refused connection, connect timeout) is reported as unreachable.
- Check each link with a GET, following redirects, and sort it:
    - ok: a status below 400 at the same URL.
    - redirected: a status below 400 at another URL; add a note when a specific page redirects to a site's front page (the page may be gone).
    - broken: a 4xx or 5xx status other than 401, 403 and 429.
    - blocked: 401, 403 or 429 (refused this client; may work in a browser).
    - unreachable: no answer (DNS failure, timeout, refused connection).
    - skipped_robots: not fetched because of robots.txt.
- With --wayback, look up the most recent Wayback Machine copy of each broken or unreachable link, at least 3 seconds apart, and stop at the first rate-limit answer (the rest say they weren't looked up).
- Report on the page's own robots.txt the way url_content.py --warn-robots does: whether its site opts out of AI input, and whether it asks automated clients not to fetch the page.
- Output:
    - {{Page URL}}, {{Final URL}} if redirected, and any robots.txt notes about the page.
    - {{Links Found}}, {{Links Checked}}, and what was left out and why.
    - {{Count}} per status.
    - Broken, unreachable, blocked and robots-skipped links, each with {{Status Code}} {{Reason}} or {{Error}}, {{URL}} and {{Link Text}}, plus the archived copy when looked up.
    - Redirected links with {{Final URL}} and any note.
    - With --json: {url, final_url, link_count, checked, max_links, scope, counts, skipped, ai_input_warning, robots_disallow_note, links: [{url, text, internal, status, status_code, reason, final_url, error, note, archived?, archive_error?}]}.
- A page with broken links is a normal result.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without. Only a failure to fetch the page itself (or a page that isn't HTML) counts.
    - An invalid option value exits with code 2, before any network call.
