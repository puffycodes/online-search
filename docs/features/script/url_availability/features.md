# URL Availability

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use cli_utils.py's validate_url_scheme().

## Actions

- Run as python3 url_availability.py from the repo root.
- Take:
    - {{URL}}: must start with http:// or https://; anything else is rejected before any request.
    - A request timeout in seconds (default: 10), also used for the Wayback Machine lookup.
    - An optional --wayback flag (off by default).
- Request the page with GET (not HEAD, which some servers mishandle), following redirects and timing the request.
- Classify the result:
    - A status below 400 is available; 4xx or 5xx is not available.
    - A connection failure (DNS, timeout, refused) is an error, not "not available" (unless --wayback is given; see below).
- With --wayback, when the page is not available:
    - Look up its most recent snapshot with the Wayback Machine availability API (archive.org, no API key).
    - Report {{Archived URL}}, {{Archived At}} (UTC) and {{Archived Status}} (the page's status when archived), or that there is no archived copy.
    - If the lookup fails (e.g. rate limiting), report why; the check itself still succeeds.
    - A connection failure is reported as a result rather than an error exit: not available, with {{Connection Error}}.
    - Never look up a page that is available, and never look up without the flag.
- Output:
    - {{URL}} is available / not available ({{Status Code}} {{Reason}})
    - {{Final URL}}, after redirects.
    - {{Response Time}}
    - With --json: {url, available, status_code, reason, final_url, elapsed_ms}.
        - With --wayback and a page that is not available, also: archived ({url, timestamp, archived_at, status} or null), archive_error (null or the reason), and error (the connection error) when the server couldn't be reached, with status_code, reason, final_url and elapsed_ms null.
- Check reachability only, not the page's content.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
