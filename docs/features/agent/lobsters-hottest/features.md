# Lobsters Hottest

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the lobsters_hottest.py script to retrieve the top discussions.
    - For Hacker News, use the hottest-tech-discussions agent instead.

## Actions

- Look up the top n hottest discussions on Lobsters.
    - n is a number given by the user.
    - If n is not given, the default is ten (10).
    - Exclude a tag only when the user asks to leave out a kind of story, e.g. "meta" for posts about the site itself.
- If the lookup fails, report the error. Retry at most once, only for a transient network error.
- Output a numbered list, one discussion per entry:
    - {{Rank}} {{Title}}
    - {{Score}} {{Number of Comments}} {{Tags}}
    - {{Discussion Link}}, and {{Article Link}} if it differs and is useful.
    - {{Excluded Tags}}, if any were left out.
- Don't compare scores with Hacker News; Lobsters is much smaller.
- If no discussions are returned, say so plainly.
- Never fabricate discussions or figures.
