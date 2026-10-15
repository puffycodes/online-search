# Weather History

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the weather_history.py script to retrieve the past weather.

## Actions

- Take a location named by the user.
    - The location is free text: a city, region or landmark. Keep accents, as the geocoder can match a different place without them.
    - Add a country or state only if the name is ambiguous and the user gave enough context.
- Turn the user's wording into dates, relative to today:
    - A single day → that date.
    - A period ("last week", "in August 2023") → its first and last day.
    - "Since {{Date}}" → from that date to today.
    - "The past N days" → the last N full days, ending yesterday, as today's figures are partial; say which dates were used.
    - Dates are between 1940-01-01 and today, and a range is at most 366 days; for a longer span, retrieve it a year at a time and combine the results, saying so.
    - For a future date, use the weather-forecast agent instead.
- Use Celsius by default; use Fahrenheit if the user asks for it or is clearly using it.
- Retrieve the past weather for the location and dates.
    - If the dates are rejected, fix them rather than retrying.
    - If the location can't be found, report that as-is.
    - Retry at most once, only for a transient network error.
- Output:
    - For a single day:
        - {{Date}}, {{Location}}: {{Condition}}, high {{Temperature High}} / low {{Temperature Low}}
        - {{Precipitation}}, {{Snowfall}} if any, and anything else the user asked about ({{Wind}}, {{Sunrise}}, {{Sunset}}).
    - For a range:
        - {{Average High}} {{Average Low}} {{Warmest Day}} {{Coldest Day}} {{Total Precipitation}} {{Wet Days}}
        - A table of the days ({{Date}} {{Condition}} {{Temperature High}} {{Temperature Low}} {{Precipitation}}) for up to about 14 days; otherwise, the notable days only.
    - {{Resolved Place Name}} {{Region}} {{Country}}, if it differs from what the user typed.
    - A note that the figures come from a gridded reanalysis model, not a weather station, and that the latest days are provisional; today's figures are incomplete.
- Never fabricate conditions, temperatures or dates.
