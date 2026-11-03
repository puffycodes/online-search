# URL Content

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the url_content.py script to retrieve the page.

## Actions

- Take a URL given by the user.
    - If it has no http:// or https://, add https://.
- Retrieve the page content.
    - Extract readable text when the user wants to read, summarize or extract information; otherwise return the raw content.
    - The content is cut at 20,000 characters by default.
    - Report errors (4xx/5xx, non-text content such as images or PDFs, connection failures) plainly.
    - Retry at most once, only for a transient network error.
    - Always note what the site's robots.txt asks (the noting mode, not the refusing check): the user chose the page, but an AI will read it.
- Output:
    - If the site opts out of AI input, or its robots.txt asks automated tools not to fetch the page (the softer note), one plain line saying so before anything else (e.g. "Note: example.com asks AI tools not to use its content (its robots.txt says `Content-Signal: ai-input=no`)."); then the answer as usual, not dropped or watered down. Nothing when it doesn't.
    - A summary of, or quotes from, {{Content}}, as the request calls for. Show the full page source only if asked.
    - If {{Content}} was cut off, say so and offer to fetch more.
    - Note, when relevant, that raw content includes HTML markup, that JavaScript-heavy pages may look sparse, and that extracted text can include navigation and footers.
- Never fabricate page content, status codes or URLs.
