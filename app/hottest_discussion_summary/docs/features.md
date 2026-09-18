# Create Summaries for the Hottest Discussion of the Day

## Requirement

- Use the scripts or agents in this project as much as possible.

## Actions

- Look up the top three topics of hottest tech discussion.
- For each of the topics:
    - Make a summary of the discussion.
        - Retrieve the content from the link(s) in the topics.
        - Produce a summary using the content.
    - Identify the subject of the discussion and express it as a single phase.
    - Provide more information on the subject of discussion.
        - Use the subject of the discussion to do web search to obtain 3 results each from 2 separate search sources.
        - Retrieve the content of each of the results and give a summary using all of the content.
- Output:
    - Time stamped the output to differentiate it from the summaries from other days.
    - For each of the topics:
        - Show the discussion topic, the link(s), and the summary
        - Show the subject of discussion that has been identified.
            - Show the summary of the search together with the links to the search result.
- Give the user the following choices after the completion of the above:
    - Publish the summary as an artifact.
    - Save the summary as a local HTML file or a markdown file.
    - Do nothing further.
