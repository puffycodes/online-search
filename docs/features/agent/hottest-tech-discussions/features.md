# Hottest Tech Discussions

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the hottest_tech_discussions.py script to retrieve the top discussions.

## Actions

- Look up the top n hottest tech discussions on Hacker News.
    - n is a number given by the user.
    - If n is not given, the default is ten (10).
- If the lookup fails, report the error. Retry at most once.
- Output a numbered list, one discussion per entry:
    - {{Rank}} {{Title}}
    - {{Score}} {{Number of Comments}}
    - {{Discussion Link}}, and {{Article Link}} if useful.
- If no discussions are returned, say so plainly.
- Never fabricate discussions or figures.
