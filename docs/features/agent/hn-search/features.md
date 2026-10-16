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
- Keep comment searches on topic, since a word is matched in any sense (an everyday word, another product, a person, a username):
    - Prefer searching inside {{Topic}}'s own threads (found by a story search) over searching all comments.
    - Give an ambiguous name one context word that only fits the meaning wanted (e.g. swift xcode, bun node, golang for Go), and check the first results: a context word can bring in a meaning of its own, skill-list words pull in job posts, and matches drop sharply (don't quote the narrowed total as how often HN mentions the bare name). Distinctive names need none.
    - A context word biases the sample towards its own topic (e.g. swift xcode finds Xcode complaints), and none is neutral. For opinions, rely on the topic's own threads and use context-word searches only to add recent views. Run two with different context words, give more weight to views found in both, and never report a context word's topic as a finding.
    - The monthly job threads (Who is hiring?, Who wants to be hired?, Freelancer? Seeking freelancer?) are left out by the search itself; include them only when the user asks about jobs or hiring demand.
    - Skip comments that use the word in another sense or matched only on their author's name; ask for more results than needed so enough remain.
- Choose the order: by relevance to find the big threads, by date for "lately" or "latest".
- Turn the user's wording into a date window relative to today, a minimum score, or an author, if given.
- To summarize a particular thread (one the user links, or the biggest one a search found), read it: its top comments in HN's ranked order, with a few replies under each; read more for a very large thread.
    - For "what does HN think of {{Topic}}", find the biggest threads, read the top one or two, and search recent comments.
    - For "what did people in {{Thread}} say about {{Topic}}", search all of that thread's comments for the topic (the story's id, not a comment's).
- Search Hacker News.
    - If the options are rejected, fix them rather than retrying.
    - Retry at most once, only for a transient network error.
- Output:
    - For threads, a numbered list: {{Title}} {{Score}} {{Number of Comments}} {{Posted Date}} {{Discussion Link}}, and {{Article Link}} if different. {{Total Matches}} where useful.
    - For a thread: {{Title}} {{Score}} {{Total Comments}}, how many of the highest-ranked comments were read, and a summary of their views; the top comment sets the tone but isn't a majority view.
    - For opinions, a summary of the views in the comments retrieved, grouping similar ones and noting disagreement, with links to the comments or threads used, how many comments it is based on, and how many were skipped as off-topic. It is a sample, not a consensus.
- If nothing matches, say so and suggest or run a broader search. If a thread doesn't exist, say so.
- Never fabricate threads, comments, scores or quotes.
