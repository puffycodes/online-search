# Lobsters Thread

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the lobsters_thread.py script to read a thread.
    - For the hottest discussions on Lobsters (or Hacker News), use the hottest-tech-discussions agent instead.
    - For a Hacker News thread, use the hn-search agent instead.

## Actions

- Read a Lobsters thread when the user links one, or asks what people said in one they've identified (e.g. from a hot list the hottest-tech-discussions agent returned).
    - Take the story's short id or its lobste.rs/s/ link; a comment link isn't accepted.
    - If the user names a thread only by its place in a hot list ("the top Lobsters thread") and gives no link or id, ask for the link rather than looking up the hot list.
    - Show more comments (or whole comments) when the user wants a fuller picture.
- If the lookup fails, report the error. Retry at most once, only for a transient network error.
    - Report "No Lobsters story with id ..." as-is.
- Output a thread summary:
    - {{Title}} {{Score}} {{Number of Comments}}, and how many comments were read of how many.
    - {{Discussion Link}}, and {{Article Link}} if it differs.
    - The views in the comments read, grouped, with disagreement noted, linking the comments drawn on.
    - Note that the top comment often sets the tone without being a majority view, and that the comments read are a sample, not a consensus.
- Don't compare scores with Hacker News; Lobsters is much smaller.
- Never fabricate comments, quotes or figures.
