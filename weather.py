#!/usr/bin/env python3
"""
Look up the current weather for a named location, using Open-Meteo's
public geocoding and forecast APIs (https://open-meteo.com/).

No API key required.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json

import requests

from cli_utils import die

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 10

# WMO weather interpretation codes -> short description.
# https://open-meteo.com/en/docs#weathervariables
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def fetch_json(url, params):
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def geocode(location):
    """Resolve a free-text location name to its best-matching place, or
    None if nothing matches."""
    data = fetch_json(GEOCODING_URL, {"name": location, "count": 1})
    results = data.get("results") or []
    return results[0] if results else None


def fetch_current_weather(latitude, longitude, unit="celsius"):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current_weather": "true",
        "temperature_unit": unit,
    }
    data = fetch_json(FORECAST_URL, params)
    return data.get("current_weather") or {}


def weather_description(code):
    return WEATHER_CODES.get(code, f"Unknown (code {code})")


def get_weather(location, unit="celsius"):
    """Look up a location and return its current weather as a flat
    dict, or None if the location can't be found."""
    place = geocode(location)
    if place is None:
        return None

    current = fetch_current_weather(place["latitude"], place["longitude"], unit=unit)

    return {
        "location": place.get("name"),
        "admin1": place.get("admin1"),
        "country": place.get("country"),
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "temperature": current.get("temperature"),
        "unit": "°C" if unit == "celsius" else "°F",
        "windspeed": current.get("windspeed"),
        "winddirection": current.get("winddirection"),
        "weather_code": current.get("weathercode"),
        "condition": weather_description(current.get("weathercode")),
        "time": current.get("time"),
    }


def format_place(row):
    """Assemble a "City, Region, Country" label from a geocoded record.

    Shared by format_weather() here and format_forecast() in
    weather_forecast.py; the region is dropped when it just repeats the
    location name, and the country is appended when present.
    """
    place = row["location"]
    if row.get("admin1") and row["admin1"] != row["location"]:
        place = f"{place}, {row['admin1']}"
    if row.get("country"):
        place = f"{place}, {row['country']}"
    return place


def format_weather(row):
    """Render a get_weather() record as a human-readable text block."""
    place = format_place(row)

    lines = [
        f"Weather for {place}",
        f"  Condition: {row['condition']}",
        f"  Temperature: {row['temperature']}{row['unit']}",
        f"  Wind: {row['windspeed']} km/h, direction {row['winddirection']}°",
        f"  As of: {row['time']}",
    ]
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Look up the current weather for a named location."
    )
    parser.add_argument(
        "location",
        help='Location name, e.g. "London", "New York", "Tokyo"',
    )
    parser.add_argument(
        "--unit",
        choices=["celsius", "fahrenheit"],
        default="celsius",
        help="Temperature unit (default: celsius)",
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
        print(f"Looking up the weather for '{args.location}'...\n")

    try:
        row = get_weather(args.location, unit=args.unit)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    if row is None:
        die(f"No location found matching '{args.location}'.", args.json)

    if args.json:
        print(json.dumps(row, indent=2))
        return

    print(format_weather(row))


if __name__ == "__main__":
    main()
