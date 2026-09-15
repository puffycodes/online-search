#!/usr/bin/env python3
"""
Look up the current air quality for a named location, using Open-Meteo's
public geocoding and air quality APIs (https://open-meteo.com/).

No API key required.

Requires weather.py (in this same directory) for geocoding - imported
directly rather than shelling out.

Reports both the US AQI (EPA scale, the "AQI" most commonly referenced
in US media and apps) and the European AQI (EAQI scale) alongside the
raw pollutant concentrations. The two indices use different breakpoints
and are not directly comparable - see the module-level AQI_CATEGORIES
comment for the US AQI band definitions.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json

import requests

from cli_utils import die
from weather import fetch_json, format_place, geocode

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

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


def get_air_quality(location):
    """Look up a location and return its current air quality as a flat
    dict, or None if the location can't be found."""
    place = geocode(location)
    if place is None:
        return None

    current = fetch_current_air_quality(place["latitude"], place["longitude"])
    us_aqi = current.get("us_aqi")

    return {
        "location": place.get("name"),
        "admin1": place.get("admin1"),
        "country": place.get("country"),
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "us_aqi": us_aqi,
        "us_aqi_category": us_aqi_category(us_aqi),
        "european_aqi": current.get("european_aqi"),
        "pm2_5": current.get("pm2_5"),
        "pm10": current.get("pm10"),
        "carbon_monoxide": current.get("carbon_monoxide"),
        "nitrogen_dioxide": current.get("nitrogen_dioxide"),
        "sulphur_dioxide": current.get("sulphur_dioxide"),
        "ozone": current.get("ozone"),
        "time": current.get("time"),
    }


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
        f"  As of: {row['time']}",
    ]
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Look up the current air quality for a named location."
    )
    parser.add_argument(
        "location",
        help='Location name, e.g. "London", "New York", "Tokyo"',
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if not args.json:
        print(f"Looking up air quality for '{args.location}'...\n")

    try:
        row = get_air_quality(args.location)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    if row is None:
        die(f"No location found matching '{args.location}'.", args.json)

    if args.json:
        print(json.dumps(row, indent=2))
        return

    print(format_air_quality(row))


if __name__ == "__main__":
    main()
