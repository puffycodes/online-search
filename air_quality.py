#!/usr/bin/env python3
"""
Look up the current air quality for a named location, using Open-Meteo's
public geocoding and air quality APIs (https://open-meteo.com/). With
--forecast, report each coming day's worst hour instead (US AQI, European
AQI, pollen); forecast values run about 4-5 days ahead, pollen about 3.

No API key required.

Requires weather.py (in this same directory) for geocoding - imported
directly rather than shelling out.

Reports both the US AQI (EPA scale, the "AQI" most commonly referenced
in US media and apps) and the European AQI (EAQI scale) alongside the
raw pollutant concentrations. The two indices use different breakpoints
and are not directly comparable - see the module-level AQI_CATEGORIES
comment for the US AQI band definitions.

Also reports pollen counts (grains/m³) for six plant types. Open-Meteo
only models pollen for Europe: elsewhere every pollen value is None, and
in Europe out of season they are 0.0.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json

import requests

from cli_utils import die, use_utf8_output
from weather import ATTRIBUTION, fetch_json, format_place, geocode, place_fields

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Plant types Open-Meteo reports pollen for, each as "<type>_pollen" in
# grains/m³. Europe only (CAMS European model); None elsewhere.
POLLEN_TYPES = ["alder", "birch", "grass", "mugwort", "olive", "ragweed"]
POLLEN_FIELDS = [f"{plant}_pollen" for plant in POLLEN_TYPES]

CURRENT_FIELDS = ",".join(
    [
        "us_aqi",
        "european_aqi",
        "pm2_5",
        "pm10",
        "carbon_monoxide",
        "nitrogen_dioxide",
        "sulphur_dioxide",
        "ozone",
        *POLLEN_FIELDS,
    ]
)

# US AQI (EPA) category bands: (upper bound inclusive, label).
# https://www.airnow.gov/aqi/aqi-basics/
US_AQI_CATEGORIES = [
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for Sensitive Groups"),
    (200, "Unhealthy"),
    (300, "Very Unhealthy"),
    (float("inf"), "Hazardous"),
]


def us_aqi_category(us_aqi):
    """Map a US AQI value to its EPA category label, or None if us_aqi is None."""
    if us_aqi is None:
        return None
    for upper_bound, label in US_AQI_CATEGORIES:
        if us_aqi <= upper_bound:
            return label
    return US_AQI_CATEGORIES[-1][1]


def fetch_current_air_quality(latitude, longitude):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": CURRENT_FIELDS,
        "timezone": "auto",
    }
    data = fetch_json(AIR_QUALITY_URL, params)
    return data.get("current") or {}


# The forecast is hourly only. The API accepts up to 7 days, but values run
# out after about 4-5 days (pollen after about 3); later hours are null.
MAX_FORECAST_DAYS = 7
HOURLY_FIELDS = ",".join(["us_aqi", "european_aqi", *POLLEN_FIELDS])


FORECAST_NOTE = (
    "Forecast values run out after about 4-5 days (pollen after about 3, and only in Europe)."
)


def fetch_hourly_air_quality(latitude, longitude, start=None, end=None):
    """The ``hourly`` block of the air-quality forecast: from ``start`` to
    ``end`` (dates, inclusive, local time) when given, as trip_weather.py
    asks, otherwise every forecast day from the place's today."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": HOURLY_FIELDS,
        "timezone": "auto",
    }
    if start is not None and end is not None:
        params["start_date"] = start.isoformat()
        params["end_date"] = end.isoformat()
    else:
        params["forecast_days"] = MAX_FORECAST_DAYS
    data = fetch_json(AIR_QUALITY_URL, params)
    return data.get("hourly") or {}


def daily_maxima(hourly):
    """Each local day's worst hour from fetch_hourly_air_quality()'s block.

    Returns {date: {us_aqi, us_aqi_category, european_aqi, <plant>_pollen...,
    hours}}, where each value is the day's maximum over the hours that have
    one (None if none do) and ``hours`` counts the hours with a US AQI, so
    a day the forecast only partly covers can be told apart. Days with no
    value at all are left out.
    """
    times = hourly.get("time") or []
    fields = ["us_aqi", "european_aqi", *POLLEN_FIELDS]
    days = {}
    for i, stamp in enumerate(times):
        date = stamp.split("T", 1)[0]
        day = days.setdefault(date, {field: [] for field in fields})
        for field in fields:
            values = hourly.get(field) or []
            value = values[i] if i < len(values) else None
            if value is not None:
                day[field].append(value)
    result = {}
    for date, values in days.items():
        if not any(values[field] for field in fields):
            continue
        maxima = {field: max(values[field]) if values[field] else None for field in fields}
        maxima["us_aqi_category"] = us_aqi_category(maxima["us_aqi"])
        maxima["hours"] = len(values["us_aqi"])
        result[date] = maxima
    return result


def get_air_quality(location):
    """Look up a location and return its current air quality as a flat
    dict, or None if the location can't be found."""
    place = geocode(location)
    if place is None:
        return None

    current = fetch_current_air_quality(place["latitude"], place["longitude"])
    us_aqi = current.get("us_aqi")

    return {
        **place_fields(place),
        "us_aqi": us_aqi,
        "us_aqi_category": us_aqi_category(us_aqi),
        "european_aqi": current.get("european_aqi"),
        "pm2_5": current.get("pm2_5"),
        "pm10": current.get("pm10"),
        "carbon_monoxide": current.get("carbon_monoxide"),
        "nitrogen_dioxide": current.get("nitrogen_dioxide"),
        "sulphur_dioxide": current.get("sulphur_dioxide"),
        "ozone": current.get("ozone"),
        **{field: current.get(field) for field in POLLEN_FIELDS},
        "time": current.get("time"),
    }


def get_air_quality_forecast(location):
    """Look up a location and return its daily air-quality forecast (each
    day's worst hour, see daily_maxima()) as a dict, or None if the
    location can't be found."""
    place = geocode(location)
    if place is None:
        return None

    hourly = fetch_hourly_air_quality(place["latitude"], place["longitude"])
    days = [{"date": date, **air} for date, air in sorted(daily_maxima(hourly).items())]
    return {**place_fields(place), "days": days, "note": FORECAST_NOTE}


def format_day_pollen(air):
    """A day's pollen maxima as "birch 3.2, grass 1", "none" (all zero) or
    "-" (no pollen data: outside Europe, or past the pollen forecast)."""
    counts = [(plant, air.get(f"{plant}_pollen")) for plant in POLLEN_TYPES]
    known = [(plant, value) for plant, value in counts if value is not None]
    if not known:
        return "-"
    present = [f"{plant} {value:g}" for plant, value in known if value > 0]
    return ", ".join(present) if present else "none"


def forecast_table(dated):
    """Table lines for (date, daily_maxima() entry) pairs: worst US AQI and
    its category, worst European AQI and pollen, marking a day the forecast
    covers only partly. Shared with trip_weather.py."""
    def cell(value, width):
        return f"{'-' if value is None else value:>{width}}"

    header = f"{'Date':<12}{'US AQI':>8}  {'Category':<32}{'EU AQI':>8}  Pollen (grains/m³)"
    lines = [header, "-" * len(header)]
    for date, air in dated:
        partial = f"  [{air['hours']} h of forecast]" if air["hours"] < 24 else ""
        lines.append(
            f"{date:<12}{cell(air['us_aqi'], 8)}  {air['us_aqi_category'] or '-':<32}"
            f"{cell(air['european_aqi'], 8)}  {format_day_pollen(air)}{partial}"
        )
    return lines


def format_forecast(row):
    """Render a get_air_quality_forecast() record as a human-readable table."""
    lines = [f"Air quality forecast for {format_place(row)} (each day's worst hour)", ""]
    if row["days"]:
        lines += forecast_table((day["date"], day) for day in row["days"])
    else:
        lines.append("No forecast values returned.")
    lines += ["", f"Note: {row['note']}"]
    return "\n".join(lines)


def format_pollen(row):
    """Render a record's pollen counts as one line, or say they aren't
    available when every value is None (outside Europe)."""
    values = [row.get(field) for field in POLLEN_FIELDS]
    if all(value is None for value in values):
        return "Pollen: not available (Europe only)"
    counts = ", ".join(f"{plant} {value}" for plant, value in zip(POLLEN_TYPES, values))
    return f"Pollen (grains/m³): {counts}"


def format_air_quality(row):
    """Render a get_air_quality() record as a human-readable text block."""
    place = format_place(row)

    lines = [
        f"Air quality for {place}",
        f"  US AQI: {row['us_aqi']} ({row['us_aqi_category']})",
        f"  European AQI: {row['european_aqi']}",
        f"  PM2.5: {row['pm2_5']} µg/m³",
        f"  PM10: {row['pm10']} µg/m³",
        f"  Carbon monoxide: {row['carbon_monoxide']} µg/m³",
        f"  Nitrogen dioxide: {row['nitrogen_dioxide']} µg/m³",
        f"  Sulphur dioxide: {row['sulphur_dioxide']} µg/m³",
        f"  Ozone: {row['ozone']} µg/m³",
        f"  {format_pollen(row)}",
        f"  As of: {row['time']}",
    ]
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Look up the current air quality (or, with --forecast, the "
                    "daily forecast) for a named location."
    )
    parser.add_argument(
        "location",
        help='Location name, e.g. "London", "New York", "Tokyo"',
    )
    parser.add_argument(
        "--forecast",
        action="store_true",
        help="Report each coming day's worst hour (US AQI, European AQI, pollen) "
             "instead of current conditions; values run about 4-5 days ahead.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    if not args.json:
        what = "the air quality forecast" if args.forecast else "air quality"
        print(f"Looking up {what} for '{args.location}'...\n")

    lookup = get_air_quality_forecast if args.forecast else get_air_quality
    try:
        row = lookup(args.location)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    if row is None:
        die(f"No location found matching '{args.location}'.", args.json)

    row["attribution"] = ATTRIBUTION
    if args.json:
        print(json.dumps(row, indent=2))
        return

    print(format_forecast(row) if args.forecast else format_air_quality(row))
    print(f"\n{ATTRIBUTION}")


if __name__ == "__main__":
    main()
