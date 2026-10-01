# URL Summary

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the url_content.py script to retrieve each page.

## Actions

- Take one or more URLs given by the user.
    - If a URL has no http:// or https://, add https://.
- For each URL:
    - Retrieve the page as readable text, up to 6,000 characters (more only if the user needs a long page's later sections).
    - If it fails, retry at most once for a transient network error; otherwise keep it in the report as failed, with the reason.
- Output:
    - For each URL, in the order given:
        - {{URL}}
        - {{Summary}} of the main points of what the page actually says.
        - Note if the content was cut off, and offer to fetch more.
    - For several URLs, a short combined take, only if the pages are genuinely related.
    - Every URL the user gave is accounted for, including the ones that failed.
- Never fabricate content or summarize a page that couldn't be retrieved.
