# URL Feed

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the url_feed.py script.

## Actions

- Take a feed URL, a site URL, or a site's name from the user.
    - Add https:// to a bare domain.
    - For a URL the user gave, read it with --warn-robots.
    - For a site the user only named, choose its URL, say which, and read it with --respect-robots (the repo's rule for URLs an agent chooses). If unsure of the address, say so rather than guessing.
    - Set how many items and from which date from the request; with a date, raise the item limit (e.g. 100) unless the user asked for a number, so the date decides what is shown.
- If the feed can't be read, report why; retry at most once, only for a transient network error. If a site has no feed, say so; never scrape its pages instead.
- Output:
    - {{Feed Title}} and what is shown, and the page the feed was found on when discovered.
    - A one-line robots.txt note when the tool reports one.
    - Per item, newest first: {{Title}} as a link, {{Date}} (or "undated"), {{Author}}, a one-line gist of {{Summary}}.
    - With a date: say if nothing falls in the window, mention undated items left out, and say when the feed doesn't reach back that far.
- A feed summary is the publisher's blurb, not the article; point to the url-summary agent to summarize posts.
- Never fabricate items, dates or links.
