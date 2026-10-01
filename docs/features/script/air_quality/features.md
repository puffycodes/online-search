# Air Quality

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Open-Meteo air quality API (no API key).
- Use weather.py's geocode().

## Actions

- Run as python3 air_quality.py from the repo root.
- Take:
    - {{Location}}: free text, e.g. "Beijing", "Delhi".
- Resolve the location to its top geocoding match.
    - If nothing matches, fail with "No location found matching '{{Location}}'."
- Retrieve the current air quality at that place.
- Map the US AQI to its EPA category: Good, Moderate, Unhealthy for Sensitive Groups, Unhealthy, Very Unhealthy or Hazardous.
- Never combine the US AQI and the European AQI; they use different scales.
- Output:
    - {{Place Name}}, {{Region}}, {{Country}}
    - {{US AQI}} ({{US AQI Category}}) {{European AQI}}
    - {{PM2.5}} {{PM10}} {{Carbon Monoxide}} {{Nitrogen Dioxide}} {{Sulphur Dioxide}} {{Ozone}}, in µg/m³
    - {{Observation Time}}
    - With --json: {location, admin1, country, latitude, longitude, us_aqi, us_aqi_category, european_aqi, pm2_5, pm10, carbon_monoxide, nitrogen_dioxide, sulphur_dioxide, ozone, time}.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
