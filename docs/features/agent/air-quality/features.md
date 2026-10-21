# Air Quality

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the air_quality.py script to retrieve the current air quality, and its --forecast option for coming days.

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
    - {{Alder Pollen}} {{Birch Pollen}} {{Grass Pollen}} {{Mugwort Pollen}} {{Olive Pollen}} {{Ragweed Pollen}}, in grains/m³, only if the user asks about pollen, hay fever or allergies.
        - If every pollen value is missing, say pollen counts aren't available for that place (they are only modelled for Europe). Don't report them as zero.
        - Report raw counts only; don't label them low, moderate or high.
    - {{Resolved Place Name}} {{Region}} {{Country}}, if it differs from what the user typed.
- For coming days ("tomorrow", "this weekend", "the next few days"), use the forecast:
    - {{Date}} {{US AQI}} ({{US AQI Category}}) per day, as each day's worst hour, with the worst day called out.
    - Flag a day the forecast covers only partly; if the user asks about a day beyond the last one returned, say the forecast doesn't reach that far (about 4-5 days, pollen about 3).
- If the user asks for past air quality, say it isn't available.
- End with a short credit line naming Open-Meteo.com: its data is CC BY 4.0, which requires attribution.
- Never fabricate AQI values, pollutant levels, pollen counts or locations.
