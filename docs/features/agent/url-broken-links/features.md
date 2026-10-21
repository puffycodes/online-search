# URL Broken Links

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the url_broken_links.py script to check the page's links, and its --wayback option to find archived copies.

## Actions

- Take a page URL given by the user.
    - If it has no http:// or https://, add https://.
- Check the links on the page.
    - Run with a long command timeout (10 minutes): requests to one host are spaced a second apart, so 100 links can take minutes. Never lower the gap.
    - Keep the default cap of 100 links unless the user asks for more.
    - Check only internal or only external links when the user asks for one kind.
    - Look up archived copies only when the user wants replacements or archived copies.
    - If the page itself can't be fetched, report the error; retry at most once, only for a transient network error.
- Output:
    - {{Links Checked}} of {{Links Found}}, and how many are broken or unreachable.
    - Each broken or unreachable link: {{Link Text}}, {{URL}}, {{Status Code}} {{Reason}} or {{Error}}, and {{Archived URL}} with {{Archived At}} when looked up (not a working copy if its archived status isn't 200).
    - Redirects to a site's front page, as likely broken.
    - Blocked links (401, 403, 429), as refused automated checks that may work in a browser, not as broken.
    - Links not checked because of robots.txt, as a count (with the URLs if few).
    - What was left out (over the cap, outside the chosen scope), so the user knows the check wasn't exhaustive.
    - Any robots.txt note about the page itself (AI opt-out, a rule asking automated clients not to fetch it).
    - If nothing is broken, say so plainly.
- The check uses HTTP status only: a page that returns 200 with "not found" in its body counts as ok.
- Never fabricate statuses, URLs or archived copies.
