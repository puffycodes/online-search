# Weather Forecast

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the weather_forecast.py script to retrieve the multi-day forecast.

## Actions

- Take a location named by the user.
    - The location is free text: a city, region or landmark.
    - Add a country or state only if the name is ambiguous and the user gave enough context.
- Pick the number of days from what the user asked.
    - The default is 5; "tomorrow" is 2 (report the second day), "this week" is 7, "the weekend" is enough days to reach Sunday.
    - The number of days is between 1 and 16.
- Use Celsius by default; use Fahrenheit if the user asks for it or is clearly using it.
- Retrieve the forecast for the location.
    - If the location can't be found, report that as-is.
    - Retry at most once, only for a transient network error.
- Output:
    - For a single day:
        - {{Date}}, {{Location}}: {{Condition}}, high {{Temperature High}} / low {{Temperature Low}}
        - {{Chance of Rain}}, if it's above about 30%.
    - For several days, a table or list with one row per day:
        - {{Date}} {{Condition}} {{Temperature High}} {{Temperature Low}} {{Chance of Rain}}
        - Call out any day with a notably high chance of rain or a big temperature swing.
    - For a UV question: {{Peak UV Index}} {{UV Category}} for the day(s) asked, with a brief sun-protection note when the category is High or above.
    - For a sunrise, sunset or daylight question: {{Sunrise}} {{Sunset}} {{Daylight Hours}}, in the place's local time; say when it is polar night or midnight sun.
    - {{Resolved Place Name}} {{Region}} {{Country}}, if it differs from what the user typed.
- Report daily summaries only. If the user wants the weather right now, use the weather agent instead; for a past date, use the weather-history agent.
- Never fabricate conditions, temperatures or dates.
