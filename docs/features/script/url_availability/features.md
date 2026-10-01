# URL Availability

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use cli_utils.py's validate_url_scheme().

## Actions

- Run as python3 url_availability.py from the repo root.
- Take:
    - {{URL}}: must start with http:// or https://; anything else is rejected before any request.
    - A request timeout in seconds (default: 10).
- Request the page with GET (not HEAD, which some servers mishandle), following redirects and timing the request.
- Classify the result:
    - A status below 400 is available; 4xx or 5xx is not available.
    - A connection failure (DNS, timeout, refused) is an error, not "not available".
- Output:
    - {{URL}} is available / not available ({{Status Code}} {{Reason}})
    - {{Final URL}}, after redirects.
    - {{Response Time}}
    - With --json: {url, available, status_code, reason, final_url, elapsed_ms}.
- Check reachability only, not the page's content.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
