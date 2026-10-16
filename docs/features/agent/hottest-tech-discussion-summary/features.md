# Hottest Tech Discussion Summary

## Requirement

- Use the scripts or agents in this project as much as possible.

## Actions

- Look up the top n topics of hottest tech discussion.
    - n is a number given by the user.
    - If n is not given, the default is three (3).
- For each of the topics:
    - Make a summary of the discussion.
        - Read the HN thread's top comments with the hn_thread.py script (HN refuses ordinary page fetches).
        - Retrieve the linked article's content, if it has one, up to 15,000 characters.
        - Treat a page that comes back with almost no content (just a site name, a JavaScript or sign-in wall) as not retrieved.
        - Produce a summary of what the article says and what HN commenters said, with how many comments were read.
    - Identify the subject of the discussion and express it as a single phase.
    - Provide more information on the subject of discussion.
        - Use the subject of the discussion to do web search to obtain 3 results each from 2 separate search sources, skipping:
            - the topic's own article or HN thread;
            - sites that return no readable content (Reddit, Instagram, Facebook, YouTube, TikTok);
            - results clearly about a different subject (earlier releases or versions of the same product are background, not a different subject).
        - If none of a search source's results gave real content after retrieval (failed, near-empty, duplicate, or only a link to elsewhere), search it once more with a narrower phrase (the subject's own name plus what it is), and say so.
        - Say how many results were skipped, and why.
        - Retrieve the content of each of the results and give a summary using all of the content.
            - A result that redirects to a page already collected is a duplicate; replace it with the next spare result.
    - Only when the user asks how HN discussed the topics before, list the earlier HN threads on the subject:
        - Search Hacker News stories for 1-3 distinctive keywords naming the subject (its own name when it has one; not the headline or a generic category).
        - Search the last two years, up to three days before the topic was posted, so that other submissions of the same news and the topic's own thread are not counted as earlier.
        - Skip threads under 50 points. If nothing relevant is found, or only threads about the general field, try once more with a more specific name from the article (the project's or a former name, the company or author, the idea at stake), with no minimum score if the subject is small.
        - Keep only threads about the same subject (earlier releases or versions of the same product count), at most three, highest score first.
            - Don't pad the list with threads that have almost no discussion (under 20 points or no comments) when a better one exists; list tiny threads only if they are the only ones, and say so.
        - Search only; do not read or summarize the earlier threads.
- Output:
    - Time stamped the output to differentiate it from the summaries from other days.
    - Preserve and report the full link in all situation even if the content is not retrievable, so that the requester can check it out later.
    - For each of the topics:
        - Show the discussion topic, the link(s), and the summary.
        - Show the subject of discussion that has been identified.
            - Show the summary of the search, and the links from the search results, each labelled with its {{Page Title}} (from the retrieved page, unless it is missing or just the site's name; else the search engine's title).
        - If earlier threads were asked for: {{Earlier Thread Title}} {{Score}} {{Number of Comments}} {{Posted Date}} {{Discussion Link}} for each, with the {{Keywords}} and date window searched, or say that none were found.
- Give the user the following choices after the completion of the above:
    - Publish the summary as an artifact.
    - Save the summary as a local HTML file or a markdown file.
    - Do nothing further.
