# Trip Weather

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Open-Meteo forecast, historical-weather (archive) and air-quality APIs (no API key), through the other weather scripts:
    - weather.py's geocode(), place_fields(), format_place(), format_sun(), format_daylight() and ATTRIBUTION.
    - weather_forecast.py's fetch_daily_forecast() with a start and end date, and forecast_day().
    - weather_history.py's fetch_daily_history() and build_day().
    - air_quality.py's fetch_hourly_air_quality(), daily_maxima() and POLLEN_TYPES.

## Actions

- Run as python3 trip_weather.py from the repo root.
- Take:
    - {{Location}}: free text, e.g. "Paris", "Kyoto".
    - {{Start Date}} (required) and {{End Date}} (default: the start date), YYYY-MM-DD.
        - The trip starts no earlier than yesterday (UTC, as a place's today can be a day behind), ends at most a year ahead, and is at most 31 days long.
    - How many past years make up typical weather, 1 to 20 (default: 5).
    - The temperature unit: celsius (default) or fahrenheit.
- Resolve the location to its top geocoding match, once.
    - If nothing matches, fail with "No location found matching '{{Location}}'."
- For days within the 16-day forecast, retrieve the daily forecast for just those dates: condition, high and low, precipitation and its chance, wind, UV index with its WHO category, sunrise, sunset and daylight.
    - A day the forecast returns empty counts as beyond the forecast.
- For the other days, give typical weather instead, from the same calendar dates in each of the past years (one archive request per year; 29 February uses the 28th in non-leap years):
    - Average high and low, the lowest and highest of each, average precipitation, how many of those years had at least 1 mm, average snowfall, and last year's sunrise, sunset and daylight.
    - Always label it as typical weather for the named years, not a forecast.
- For days within the air-quality forecast, give each day's worst hour: US AQI with its category, European AQI, and pollen per plant (Europe only), with the number of hours covered when it's less than a day.
    - Never combine the US and European AQI.
- Output:
    - Trip weather for {{Place}}, {{Start Date}} to {{End Date}}.
    - Forecast: {{Date}} {{Condition}} {{High}} {{Low}} {{Precipitation}} {{Chance of Rain}} {{UV Index}} {{UV Category}} {{Sunrise}} {{Sunset}} {{Daylight}}
    - Typical weather, from the same dates in {{First Year}}-{{Last Year}} (not a forecast): {{Date}} {{Average High}} ({{High Range}}) {{Average Low}} ({{Low Range}}) {{Average Precipitation}} {{Wet Years}} of {{Years}} {{Sunrise}} {{Sunset}} {{Daylight}}
    - Air quality (the day's worst hour): {{Date}} {{US AQI}} {{Category}} {{European AQI}} {{Pollen}}, plus the hours covered for a partial day.
    - Notes: where typical weather starts, and that later days have no air-quality forecast.
    - With --json: {location, admin1, country, latitude, longitude, unit, start_date, end_date, typical_years, days: [{date, source ("forecast" or "typical"), ..., air}], summary: {forecast_days, typical_days, air_quality_days, forecast_wet_days, highest, lowest}, notes, attribution}.
- Always end the result with the credit "Data by Open-Meteo.com (https://open-meteo.com/), licensed under CC BY 4.0.": the last line of the report, or the `attribution` field with --json.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value or date exits with code 2, before any network call.
