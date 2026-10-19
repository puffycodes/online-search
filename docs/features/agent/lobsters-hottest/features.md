# Lobsters Hottest

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the lobsters_hottest.py script to retrieve the top discussions.
    - Use the lobsters_thread.py script to read a thread.
    - For Hacker News, use the hottest-tech-discussions or hn-search agent instead.

## Actions

- Look up the top n hottest discussions on Lobsters.
    - n is a number given by the user.
    - If n is not given, the default is ten (10).
    - Exclude a tag only when the user asks to leave out a kind of story, e.g. "meta" for posts about the site itself.
- Read a thread when the user links one or asks what people said in one from the hot list.
    - Take the story's short id or its lobste.rs/s/ link; a comment link isn't accepted.
    - Show more comments (or whole comments) when the user wants a fuller picture.
- If a lookup fails, report the error. Retry at most once, only for a transient network error.
    - Report "No Lobsters story with id ..." as-is.
- Output the hot list as a numbered list, one discussion per entry:
    - {{Rank}} {{Title}}
    - {{Score}} {{Number of Comments}} {{Tags}}
    - {{Discussion Link}}, and {{Article Link}} if it differs and is useful.
    - {{Excluded Tags}}, if any were left out.
- Output a thread summary:
    - {{Title}} {{Score}} {{Number of Comments}}, and how many comments were read of how many.
    - The views in the comments read, grouped, with disagreement noted, linking the comments drawn on.
    - Note that the top comment often sets the tone without being a majority view, and that the comments read are a sample, not a consensus.
- Don't compare scores with Hacker News; Lobsters is much smaller.
- If no discussions are returned, say so plainly.
- Never fabricate discussions, comments, quotes or figures.
