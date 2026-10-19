# Hottest Discussions

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the hottest_tech_discussions.py script to retrieve the top discussions.

## Actions

- Upon starting, do not display any top discussions.
- Display a drop-down menu to select how many top discussions to retrieve.
    - The options are 10, 25 and 50.
    - The default is 10.
- Display a button for refreshing the discussions.
- After refreshing:
    - Display the top discussions, one per discussion
        - {{Rank}} {{Title}}
            - The {{Title}} links to the discussed article.
        - {{Points}} {{Number of Comments}} {{Posted Time}} {{Discussion Link}}
    - Display the time the discussions were fetched.
