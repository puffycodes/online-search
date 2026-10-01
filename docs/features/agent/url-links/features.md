# URL Links

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the url_links.py script to extract the links.

## Actions

- Take a URL given by the user.
    - If it has no http:// or https://, add https://.
- Extract every link on the page, with relative links made absolute.
    - Report errors (4xx/5xx, non-HTML content, connection failures) plainly.
    - Retry at most once, only for a transient network error.
- If the user asked for a kind of link (e.g. PDFs, external links), filter the links before answering.
- Output:
    - {{Link Count}}, the total number of links found.
    - One entry per link: {{Link Text}} {{Link URL}}
    - Note, when relevant, that mailto:, tel: and javascript: links are included, repeated links are not removed, and links added by JavaScript are not seen.
- Never fabricate links, counts or URLs.
