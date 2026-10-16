# Hottest Tech Discussion Summary

## Requirement

- Use the scripts or agents in this project as much as possible.

## Actions

- Look up the top n topics of hottest tech discussion.
    - n is a number given by the user.
    - If n is not given, the default is three (3).
- For each of the topics:
    - Make a summary of the discussion.
        - Retrieve the content from the link(s) in the topics.
        - Produce a summary using the content.
    - Identify the subject of the discussion and express it as a single phase.
    - Provide more information on the subject of discussion.
        - Use the subject of the discussion to do web search to obtain 3 results each from 2 separate search sources.
        - Retrieve the content of each of the results and give a summary using all of the content.
    - Only when the user asks how HN discussed the topics before, list the earlier HN threads on the subject:
        - Search Hacker News stories for 1-3 distinctive keywords naming the subject (not the headline).
        - Search the last two years, up to three days before the topic was posted, so that other submissions of the same news and the topic's own thread are not counted as earlier.
        - Skip threads under 50 points; if nothing relevant is found, try once more with broader keywords or no minimum score.
        - Keep only threads about the same subject, at most three, highest score first.
        - Search only; do not read or summarize the earlier threads.
- Output:
    - Time stamped the output to differentiate it from the summaries from other days.
    - Preserve and report the full link in all situation even if the content is not retrievable, so that the requester can check it out later.
    - For each of the topics:
        - Show the discussion topic, the link(s), and the summary.
        - Show the subject of discussion that has been identified.
            - Show the summary of the search, and the links from the search results.
        - If earlier threads were asked for: {{Earlier Thread Title}} {{Score}} {{Number of Comments}} {{Posted Date}} {{Discussion Link}} for each, with the {{Keywords}} and date window searched, or say that none were found.
- Give the user the following choices after the completion of the above:
    - Publish the summary as an artifact.
    - Save the summary as a local HTML file or a markdown file.
    - Do nothing further.
