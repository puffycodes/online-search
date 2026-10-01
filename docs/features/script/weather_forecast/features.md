# Weather Forecast

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Open-Meteo forecast API (no API key).
- Use weather.py's geocode(), place_fields() and weather_description().

## Actions

- Run as python3 weather_forecast.py from the repo root.
- Take:
    - {{Location}}: free text, e.g. "Tokyo", "Long Island".
    - The number of days, 1 to 16 (default: 5).
    - The temperature unit: celsius (default) or fahrenheit.
- Resolve the location to its top geocoding match.
    - If nothing matches, fail with "No location found matching '{{Location}}'."
- Retrieve the daily forecast, with days following the location's own local calendar.
- Output, one row per day starting today:
    - {{Date}} {{Condition}} {{Temperature High}} {{Temperature Low}} {{Precipitation}} {{Chance of Rain}} {{Max Wind Speed}}
    - With --json: {location, admin1, country, latitude, longitude, unit, days: [{date, weather_code, condition, temp_max, temp_min, precipitation_sum, precipitation_probability_max, windspeed_max}]}.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
