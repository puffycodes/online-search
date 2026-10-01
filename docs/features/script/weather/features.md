# Current Weather

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Open-Meteo geocoding and forecast APIs (no API key).
- Keep geocode(), fetch_json(), format_place() and weather_description() in this script so weather_forecast.py and air_quality.py can import them.

## Actions

- Run as python3 weather.py from the repo root.
- Take:
    - {{Location}}: free text, e.g. "Tokyo", "Long Island".
    - The temperature unit: celsius (default) or fahrenheit.
- Resolve the location to its top geocoding match.
    - If nothing matches, fail with "No location found matching '{{Location}}'."
- Retrieve the current weather at that place, and turn the weather code into a short description.
- Output:
    - {{Place Name}}, {{Region}}, {{Country}}
    - {{Condition}} {{Temperature}} {{Wind Speed}} {{Wind Direction}} {{Observation Time}}
    - With --json: {location, admin1, country, latitude, longitude, temperature, unit, windspeed, winddirection, weather_code, condition, time}.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
