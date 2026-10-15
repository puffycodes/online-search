# Weather History

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Open-Meteo historical-weather (archive) API (no API key).
- Use weather.py's geocode(), fetch_json(), place_fields(), format_place(), weather_description(), daily_value(), sun_fields(), format_sun() and format_daylight().

## Actions

- Run as python3 weather_history.py from the repo root.
- Take:
    - {{Location}}: free text, e.g. "Tokyo", "Long Island".
    - Either {{Date}}, a single day, or {{Start Date}} with an optional {{End Date}} (default: today), all YYYY-MM-DD; or {{Last N}}, the last N full days ending yesterday (today's figures are partial).
    - The temperature unit: celsius (default) or fahrenheit.
- Reject the dates, before any network call, when:
    - None of a date, a start date or a last-N count is given, a date is combined with a start or end date, a last-N count is combined with any date, or an end date is given without a start date.
    - A last-N count isn't a positive whole number.
    - The end date is before the start date.
    - A date is before 1940-01-01 (the archive's first day) or after today.
    - The range is longer than 366 days.
- Resolve the location to its top geocoding match.
    - If nothing matches, fail with "No location found matching '{{Location}}'."
- Retrieve the daily weather for the dates, with days following the location's own local calendar.
- For each day: {{Date}} {{Condition}} {{Temperature High}} {{Temperature Low}} {{Temperature Mean}} {{Precipitation}} {{Rain}} {{Snowfall}} {{Max Wind Speed}} {{Sunrise}} {{Sunset}} {{Daylight}}
    - Sunrise and sunset are local "HH:MM" times and daylight is in hours; in polar night or midnight sun, leave sunrise and sunset blank and say which it is.
    - A value the archive doesn't have yet (usually today's) is left blank.
- For more than one day, a summary: {{Days}} {{Days With Data}} {{Average High}} {{Average Low}} {{Warmest Day}} {{Coldest Day}} {{Total Precipitation}} {{Wet Days}} (at least 1 mm) {{Total Snowfall}}
    - A day missing a value is left out of that value's figure.
- Output:
    - {{Place Name}}, {{Region}}, {{Country}} and the date or range.
    - One row per day, then the summary.
    - With --json: {location, admin1, country, latitude, longitude, start_date, end_date, unit, days: [{date, weather_code, condition, temp_max, temp_min, temp_mean, precipitation_sum, rain_sum, snowfall_sum, windspeed_max, sunrise, sunset, daylight_hours, polar}], summary}.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value or date exits with code 2, before any network call.
