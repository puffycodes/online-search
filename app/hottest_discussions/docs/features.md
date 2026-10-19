# Hottest Discussions

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the hottest_tech_discussions.py script to retrieve the top discussions, from Hacker News, Lobsters or both.

## Actions

- Upon starting, do not display any top discussions.
- Display a drop-down menu to select where to retrieve the top discussions from.
    - The options are Hacker News, Lobsters and All Sources (Hacker News and Lobsters).
    - The default is Hacker News.
- Display a drop-down menu to select how many top discussions to retrieve from each site.
    - The options are 10, 25 and 50.
    - The default is 10.
    - With All Sources, the number is per site, so 10 means up to 10 from each.
- Display a button for refreshing the discussions.
- After refreshing:
    - Display the top discussions in one section per site, Hacker News first, each headed with the {{Site Name}}.
        - Never rank discussions from different sites against each other or merge them into one list: their scores aren't comparable (Lobsters is much smaller).
        - If a site returns no discussions, say so in its section.
    - One entry per discussion, ranked from 1 within its site:
        - {{Rank}} {{Title}}
            - The {{Title}} links to the discussed article.
        - {{Points}} {{Number of Comments}} {{Posted Time}} {{Discussion Link}}, with the link text naming the site (e.g. "discuss on HN", "discuss on Lobsters").
        - {{Tags}}, for Lobsters discussions only.
    - Display the time the discussions were fetched, and the site(s) they came from.
- If fetching fails for any selected site, show no discussions and display an error naming the site that failed.
