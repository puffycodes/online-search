# Earthquakes

## Requirement

- Reuse the shared modules in this project (rather than copying their logic) as much as possible.
- Use the USGS earthquake catalog's event query API (https://earthquake.usgs.gov/fdsnws/event/1/, no API key).
- Use weather.py's geocode(), place_fields() and format_place(), and daily_prices.py's date window for --start / --end.

## Actions

- Run as python3 earthquakes.py from the repo root.
- Take:
    - {{Location}}: free text, e.g. "Tokyo", "San Francisco".
    - An optional --radius in km (default 300, at most 20000).
    - An optional --min-magnitude (default 2.5, from -2 to 10).
    - An optional period: --days N, the last N days ending today, 1 being today (default 30); or --start and an optional --end (UTC dates, inclusive; --end defaults to today). --days and --start can't be combined, and --end needs --start.
    - An optional --order: time (newest first, the default) or magnitude (largest first).
    - An optional --limit (default 20, at most 20000).
- Resolve the location to its top geocoding match.
    - If nothing matches, fail with "No location found matching '{{Location}}'."
- Retrieve the earthquakes within the radius of that place, at or above the magnitude, over the period, in the order asked, up to the limit.
    - Ask for one more than the limit, to tell whether more matched.
    - A rejected query is reported with the reason USGS gives (e.g. "400: Bad latitude value ...").
- For each earthquake, give its distance from the geocoded place in km.
- For a place outside the US, add a note: the USGS catalog lists few earthquakes below about magnitude 4.5 outside the US, so smaller quakes there are mostly missing, not absent.
- Output:
    - Earthquakes within {{Radius}} km of {{Place Name}}, {{Region}}, {{Country}}
    - Magnitude {{Min Magnitude}}+, {{Start Date}} to {{End Date}} (UTC), newest first / largest first
    - {{Time (UTC)}} {{Magnitude}} {{Depth}} {{Distance}} {{USGS Place Description}} per earthquake, flagged with "tsunami flag", "PAGER {{Alert Level}}" and "not yet reviewed" where they apply; or "No earthquakes found."
    - "More earthquakes match; showing the first {{Limit}} (raise --limit to see more).", when more matched.
    - Note: {{Coverage Note}}, outside the US.
    - With --json: {location, admin1, country, latitude, longitude, radius_km, min_magnitude, start, end, order, limit, count, more, earthquakes: [{time, magnitude, magnitude_type, place, latitude, longitude, depth_km, distance_km, status, tsunami, alert, felt, url}], coverage_note (outside the US only)}.
- Always end the result with the credit "Earthquake data courtesy of the U.S. Geological Survey (https://earthquake.usgs.gov/). Place lookup: Data by Open-Meteo.com (https://open-meteo.com/), licensed under CC BY 4.0." (USGS asks to be credited; Open-Meteo's CC BY 4.0 licence requires it): the last line of the report, or the `attribution` field with --json.
- Support a --json option:
    - With it, skip any progress line and print the result as a single JSON value on stdout.
    - Without it, print a human-readable report.
- Write stdout and stderr as UTF-8 on every platform, so non-ASCII text (°, accents, CJK, emoji) neither garbles nor crashes the script when output is piped on Windows.
- On failure:
    - A runtime or data failure (an unknown place, a malformed date, an end before the start, a USGS or network error) exits with code 1, with the error on stderr: {"error": "..."} with --json, or "Error: ..." without.
    - An invalid option value exits with code 2, before any network call.
