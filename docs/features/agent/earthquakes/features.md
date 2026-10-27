# Earthquakes

## Requirement

- Use the scripts or agents in this project as much as possible.
    - Use the earthquakes.py script to retrieve the earthquakes near a place.

## Actions

- Take a location named by the user, and optionally a distance, a magnitude and a period.
    - The location is free text: a city, region or landmark.
    - Add a country or state only if the name is ambiguous and the user gave enough context.
- Keep the defaults (within 300 km, magnitude 2.5 and up, the last 30 days, newest first, at most 20) unless the user's wording calls for another value:
    - A named distance → that radius (miles converted to km); a whole country or region → a radius that covers it, said in the report.
    - A named magnitude → that minimum; "big", "major" or "strong" → magnitude 5, said in the report; "any" or "even small" in the US → magnitude 1.
    - "today" → 1 day; "this week" → 7 days; "this year" → from 1 January; a named month or span → its start and end dates (UTC).
    - "the biggest" or "the strongest" → largest first.
    - "how many" or "all of them" → a higher limit, so the count isn't cut short.
- Retrieve the earthquakes.
    - If the location can't be found, report that as-is.
    - Retry at most once, only for a transient network error.
- Output:
    - The answer first, e.g. {{Count}} earthquakes of magnitude {{Min Magnitude}}+ within {{Radius}} km of {{Place}} from {{Start Date}} to {{End Date}}, and the largest.
    - The search used (radius, minimum magnitude, dates), and {{Resolved Place Name}} if it differs from what the user typed.
    - The largest and the most recent: {{Magnitude}}, {{USGS Place Description}}, {{Distance}} km away, {{Date}}; each one for a handful, a summary for many.
    - Times in UTC, said as such.
    - If more matched than were listed, say so rather than giving the listed number as the total.
    - For a quake singled out: "not yet reviewed" when USGS hasn't reviewed it; the tsunami flag, explained as USGS's flag for a large quake in an oceanic region and not a warning, pointing to official tsunami warning centres; a PAGER alert of yellow or above.
    - If none matched, say so with the search's limits; never call a place safe.
    - Outside the US, the coverage note: few quakes below about magnitude 4.5 are in the catalog there, so small quakes are missing, not absent.
- Never predict or forecast earthquakes.
- End with a short credit line naming the U.S. Geological Survey, and Open-Meteo.com for the place lookup (CC BY 4.0).
- Never fabricate earthquakes, magnitudes, times or places.
