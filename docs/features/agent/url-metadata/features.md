# URL Metadata

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the url_metadata.py script to read the metadata.

## Actions

- Take one or more URLs given by the user.
    - If a URL has no http:// or https://, add https://.
- Read each page's metadata, once per URL.
    - Report errors (4xx/5xx, non-HTML content, connection failures) plainly.
    - Retry at most once, only for a transient network error.
- Output:
    - What the user asked for first (e.g. just the title, or whether there is a preview image).
    - Otherwise: {{Title}} {{Description}} {{Canonical URL}}, then the OpenGraph and Twitter card tags.
    - For a link-preview question: which values a preview would use ({{OG Title}} {{OG Description}} {{OG Image}}, falling back to the title and description) and what is missing.
    - Note when the canonical URL differs from the final URL, and when the URL redirected.
    - For several URLs, a table: {{URL}} {{Title}} and whatever else was asked, plus any URL that failed and why.
    - Note, when a well-known page returns nothing, that tags set by JavaScript are not seen.
- Never fabricate titles, descriptions, tags or URLs.
