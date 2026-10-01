# URL Availability

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the url_availability.py script to check the URL.

## Actions

- Take a URL given by the user.
    - If it has no http:// or https://, add https://.
- Check whether the URL is reachable.
    - A 4xx or 5xx status is a successful check that found the page unavailable.
    - A connection failure (DNS, timeout, refused) is an error; report it differently from a status code.
    - Retry at most once, only for a transient network error.
- Output:
    - {{URL}} is available ({{Status Code}} {{Reason}}), or {{URL}} is not available ({{Status Code}} {{Reason}})
    - {{Final URL}}, only if a redirect happened.
    - {{Response Time}}, only if asked for or notably slow.
- The check uses the HTTP status only. A page that returns 200 with an error message in it is reported as available; say so if the user is asking about the content.
- Never fabricate status codes, response times or URLs.
