# Hacker News Search

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the hn_search.py script to search Hacker News.
    - For what is trending on HN right now, use the hottest-tech-discussions agent instead.

## Actions

- Take a topic, product, person or question from the user.
    - Reduce it to a few distinctive keywords. Words are matched whole, so use the form people write; try a synonym or abbreviation if results are thin.
- Choose what to search:
    - Stories for threads and articles; comments for what people said; Ask HN or Show HN posts when asked for.
    - For "what does HN think of {{Topic}}", search both stories and comments.
- Choose the order: by relevance to find the big threads, by date for "lately" or "latest".
- Turn the user's wording into a date window relative to today, a minimum score, or an author, if given.
- Search Hacker News.
    - If the options are rejected, fix them rather than retrying.
    - Retry at most once, only for a transient network error.
- Output:
    - For threads, a numbered list: {{Title}} {{Score}} {{Number of Comments}} {{Posted Date}} {{Discussion Link}}, and {{Article Link}} if different. {{Total Matches}} where useful.
    - For opinions, a summary of the views in the comments retrieved, grouping similar ones and noting disagreement, with links to the comments or threads used and how many comments it is based on. It is a sample, not a consensus.
- If nothing matches, say so and suggest or run a broader search.
- Never fabricate threads, comments, scores or quotes.
