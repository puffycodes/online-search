# Air Quality

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the air_quality.py script to retrieve the current air quality.

## Actions

- Take a location named by the user.
    - The location is free text: a city, region or landmark.
    - Add a country or state only if the name is ambiguous and the user gave enough context.
- Retrieve the current air quality for the location.
    - If the location can't be found, report that as-is.
    - Retry at most once, only for a transient network error.
- Output:
    - {{Location}}: AQI {{US AQI}} ({{US AQI Category}})
    - {{European AQI}}, only if the location is in Europe or the user asks for it.
        - Report it side by side with the US AQI. Never average or combine the two; they use different scales.
    - {{PM2.5}} {{PM10}} {{Ozone}} {{Nitrogen Dioxide}} {{Sulphur Dioxide}} {{Carbon Monoxide}}, only if the user asks for detail or one is notably high.
    - {{Resolved Place Name}} {{Region}} {{Country}}, if it differs from what the user typed.
- Report current conditions only. If the user asks for a forecast or past air quality, say it isn't available.
- Never fabricate AQI values, pollutant levels or locations.
