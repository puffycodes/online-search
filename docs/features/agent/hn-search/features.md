# Hacker News Search

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the hn_search.py script to search Hacker News, and the hn_thread.py script to read a thread.
    - For what is trending on HN right now, use the hottest-tech-discussions agent instead.

## Actions

- Take a topic, product, person or question from the user.
    - Reduce it to a few distinctive keywords. Words are matched whole, so use the form people write; try a synonym or abbreviation if results are thin.
- Choose what to search:
    - Stories for threads and articles; comments for what people said; Ask HN or Show HN posts when asked for.
    - For "what does HN think of {{Topic}}", search both stories and comments.
- Choose the order: by relevance to find the big threads, by date for "lately" or "latest".
- Turn the user's wording into a date window relative to today, a minimum score, or an author, if given.
- To summarize a particular thread (one the user links, or the biggest one a search found), read it: its top comments in HN's ranked order, with a few replies under each; read more for a very large thread.
    - For "what does HN think of {{Topic}}", find the biggest threads, read the top one or two, and search recent comments.
- Search Hacker News.
    - If the options are rejected, fix them rather than retrying.
    - Retry at most once, only for a transient network error.
- Output:
    - For threads, a numbered list: {{Title}} {{Score}} {{Number of Comments}} {{Posted Date}} {{Discussion Link}}, and {{Article Link}} if different. {{Total Matches}} where useful.
    - For a thread: {{Title}} {{Score}} {{Total Comments}}, how many of the highest-ranked comments were read, and a summary of their views; the top comment sets the tone but isn't a majority view.
    - For opinions, a summary of the views in the comments retrieved, grouping similar ones and noting disagreement, with links to the comments or threads used and how many comments it is based on. It is a sample, not a consensus.
- If nothing matches, say so and suggest or run a broader search. If a thread doesn't exist, say so.
- Never fabricate threads, comments, scores or quotes.
