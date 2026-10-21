# Trip Weather

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the trip_weather.py script.

## Actions

- Take a place and trip dates named by the user.
    - Turn relative dates ("next week", "the first week of June", "over Christmas") into a start and end date, and say which dates were used.
    - A trip can start from yesterday up to a year ahead and last at most 31 days; split or narrow a longer stay. For past dates, use the weather-history agent.
    - Use fahrenheit only if the user asks for it or clearly expects it.
- If the place can't be found, say so; retry at most once, only for a transient network error.
- Output:
    - An overall picture first: {{Range of Highs and Lows}}, how rainy, anything notable (heat, storms, high UV, poor air).
    - Forecast days: {{Date}} {{Condition}} {{High}} {{Low}} {{Chance of Rain}}, with UV when High or above and a brief sun-protection note.
    - Typical days, kept separate and labelled as typical weather for those dates over {{First Year}}-{{Last Year}}, not a forecast: {{Average High}} {{Average Low}} with their ranges, and how many of those years were wet.
    - Air quality where forecast: {{US AQI}} {{Category}} and notable pollen; never combine the US and European AQI; say later days have no air-quality forecast.
    - Sunrise and sunset, local time, when useful.
    - {{Resolved Place}} when it differs from what the user typed.
    - Packing or planning advice only from these figures.
- Always end with a credit line for Open-Meteo, e.g. "Data: Open-Meteo.com (CC BY 4.0)".
- Never present typical weather as a forecast, and never fabricate conditions, temperatures, air quality or dates.
