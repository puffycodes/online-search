# Hottest Tech Discussions

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the hottest_tech_discussions.py script to retrieve the top discussions, from Hacker News, Lobsters or both.
    - To search past HN discussions about a topic, or to read an HN thread, use the hn-search agent instead.
    - To read a Lobsters thread, use the lobsters-thread agent instead.

## Actions

- Look up the top n hottest tech discussions.
    - n is a number given by the user, per source.
    - If n is not given, the default is ten (10).
    - Choose the sources from what the user asks:
        - Hacker News when no site is named (e.g. "what's trending in tech today").
        - Lobsters when the user names Lobsters or lobste.rs.
        - Both when the user names both, or asks across sites.
    - Exclude a Lobsters tag only when the user asks to leave out a kind of story, e.g. "meta" for posts about the site itself.
- If the lookup fails, report the error. Retry at most once.
- Output a numbered list per source, one discussion per entry:
    - {{Source Name}}, as a heading, when more than one source was asked for.
    - {{Rank}} {{Title}}
    - {{Score}} {{Number of Comments}}, and {{Tags}} for Lobsters
    - {{Discussion Link}}, and {{Article Link}} if useful.
    - {{Excluded Tags}}, if any were left out.
- Never compare scores across sources, or merge the lists into one ranking; Lobsters is much smaller than Hacker News.
- If no discussions are returned, say so plainly.
- Never fabricate discussions or figures.
