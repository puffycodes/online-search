# Air Quality

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the Open-Meteo air quality API (no API key).
- Use weather.py's geocode() and place_fields().
- Offer the hourly air-quality forecast fetch (all forecast days, or between two dates) and its reduction to each day's worst hour, and the forecast table, for trip_weather.py to reuse.

## Actions

- Run as python3 air_quality.py from the repo root.
- Take:
    - {{Location}}: free text, e.g. "Beijing", "Delhi".
    - An optional --forecast flag (off by default).
- Resolve the location to its top geocoding match.
    - If nothing matches, fail with "No location found matching '{{Location}}'."
- Retrieve the current air quality at that place.
- Map the US AQI to its EPA category: Good, Moderate, Unhealthy for Sensitive Groups, Unhealthy, Very Unhealthy or Hazardous.
- Retrieve the current pollen count for alder, birch, grass, mugwort, olive and ragweed, in grains/m³.
    - Pollen is only modelled for Europe; elsewhere every value is missing.
- Never combine the US AQI and the European AQI; they use different scales.
- Output:
    - {{Place Name}}, {{Region}}, {{Country}}
    - {{US AQI}} ({{US AQI Category}}) {{European AQI}}
    - {{PM2.5}} {{PM10}} {{Carbon Monoxide}} {{Nitrogen Dioxide}} {{Sulphur Dioxide}} {{Ozone}}, in µg/m³
    - {{Alder Pollen}} {{Birch Pollen}} {{Grass Pollen}} {{Mugwort Pollen}} {{Olive Pollen}} {{Ragweed Pollen}}, in grains/m³, on one line; or "Pollen: not available (Europe only)" when every value is missing.
    - {{Observation Time}}
    - With --json: {location, admin1, country, latitude, longitude, us_aqi, us_aqi_category, european_aqi, pm2_5, pm10, carbon_monoxide, nitrogen_dioxide, sulphur_dioxide, ozone, alder_pollen, birch_pollen, grass_pollen, mugwort_pollen, olive_pollen, ragweed_pollen, time}.
- With --forecast, instead of current conditions:
    - Retrieve the hourly forecast for every forecast day from the place's today, and give each day's worst hour: US AQI with its category, European AQI, and pollen per plant.
    - Mark a day the forecast covers only partly with its hours, and leave out days without values (they run out after about 4-5 days, pollen after about 3).
    - Output: Air quality forecast for {{Place}} (each day's worst hour), then {{Date}} {{US AQI}} {{Category}} {{European AQI}} {{Pollen}} per day, and a note on how far the forecast reaches.
    - With --json: {location, admin1, country, latitude, longitude, days: [{date, us_aqi, us_aqi_category, european_aqi, <plant>_pollen..., hours}], note}.
- Always end the result with the credit "Data by Open-Meteo.com (https://open-meteo.com/), licensed under CC BY 4.0." (Open-Meteo's data is CC BY 4.0, which requires attribution): the last line of the report, or the `attribution` field with --json.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
