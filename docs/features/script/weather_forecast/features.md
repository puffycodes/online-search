# Weather Forecast

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Open-Meteo forecast API (no API key).
- Use weather.py's geocode(), place_fields(), weather_description(), daily_value(), sun_fields(), format_sun() and format_daylight().

## Actions

- Run as python3 weather_forecast.py from the repo root.
- Take:
    - {{Location}}: free text, e.g. "Tokyo", "Long Island".
    - The number of days, 1 to 16 (default: 5).
    - The temperature unit: celsius (default) or fahrenheit.
- Resolve the location to its top geocoding match.
    - If nothing matches, fail with "No location found matching '{{Location}}'."
- Retrieve the daily forecast, with days following the location's own local calendar.
- Classify each day's maximum UV index into its WHO category: Low (0-2), Moderate (3-5), High (6-7), Very high (8-10), Extreme (11+), rounding the index half up first.
- Give sunrise and sunset as local "HH:MM" times and daylight in hours.
    - In polar night (no daylight) or midnight sun (24 hours of daylight), leave sunrise and sunset blank and say which it is.
- Output, one row per day starting today:
    - {{Date}} {{Condition}} {{Temperature High}} {{Temperature Low}} {{Precipitation}} {{Chance of Rain}} {{Max Wind Speed}}
    - Then a second table: {{Date}} {{UV Index}} {{UV Category}} {{Sunrise}} {{Sunset}} {{Daylight}}
    - With --json: {location, admin1, country, latitude, longitude, unit, days: [{date, weather_code, condition, temp_max, temp_min, precipitation_sum, precipitation_probability_max, windspeed_max, uv_index_max, uv_category, sunrise, sunset, daylight_hours, polar}]}.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
