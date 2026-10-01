# Current Weather

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the weather.py script to retrieve the current weather.

## Actions

- Take a location named by the user.
    - The location is free text: a city, region or landmark.
    - Add a country or state only if the name is ambiguous and the user gave enough context.
- Use Celsius by default; use Fahrenheit if the user asks for it or is clearly using it.
- Retrieve the current weather for the location.
    - If the location can't be found, report that as-is.
    - Retry at most once, only for a transient network error.
- Output:
    - {{Location}}: {{Condition}}, {{Temperature}}
    - {{Resolved Place Name}} {{Region}} {{Country}}, if it differs from what the user typed.
    - {{Wind Speed}} {{Wind Direction}}, only if notable or asked for.
    - {{Observation Time}}, if the user cares about how fresh the reading is.
- Report current conditions only. If the user asks for a forecast or past weather, say it isn't available.
- Never fabricate conditions, temperatures or locations.
