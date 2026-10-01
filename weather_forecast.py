#!/usr/bin/env python3
"""
Look up the multi-day weather forecast for a named location, using
Open-Meteo's public geocoding and forecast APIs (https://open-meteo.com/).

No API key required.

Requires weather.py (in this same directory) for geocoding and weather-
code descriptions — imported directly rather than shelling out.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import json

import requests

from cli_utils import die
from weather import (
    FORECAST_URL,
    fetch_json,
    format_place,
    geocode,
    weather_description,
)

DEFAULT_FORECAST_DAYS = 5
MAX_FORECAST_DAYS = 16  # Open-Meteo's own limit for the daily forecast.

DAILY_FIELDS = ",".join(
    [
        "weathercode",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "precipitation_probability_max",
        "windspeed_10m_max",
    ]
)


def fetch_daily_forecast(latitude, longitude, days=DEFAULT_FORECAST_DAYS, unit="celsius"):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": DAILY_FIELDS,
        "forecast_days": days,
        # "auto" resolves each location's own local timezone, so daily
        # buckets line up with its calendar days rather than UTC's.
        "timezone": "auto",
        "temperature_unit": unit,
    }
    data = fetch_json(FORECAST_URL, params)
    return data.get("daily") or {}


def get_forecast(location, days=DEFAULT_FORECAST_DAYS, unit="celsius"):
    """Look up a location and return its multi-day forecast as a dict,
    or None if the location can't be found."""
    place = geocode(location)
    if place is None:
        return None

    daily = fetch_daily_forecast(place["latitude"], place["longitude"], days=days, unit=unit)
    dates = daily.get("time", [])

    forecast_days = [
        {
            "date": date,
            "weather_code": daily["weathercode"][i],
            "condition": weather_description(daily["weathercode"][i]),
            "temp_max": daily["temperature_2m_max"][i],
            "temp_min": daily["temperature_2m_min"][i],
            "precipitation_sum": daily["precipitation_sum"][i],
            "precipitation_probability_max": daily["precipitation_probability_max"][i],
            "windspeed_max": daily["windspeed_10m_max"][i],
        }
        for i, date in enumerate(dates)
    ]

    return {
        "location": place.get("name"),
        "admin1": place.get("admin1"),
        "country": place.get("country"),
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "unit": "°C" if unit == "celsius" else "°F",
        "days": forecast_days,
    }


def format_forecast(row):
    """Render a get_forecast() record as a human-readable table."""
    place = format_place(row)

    header = (
        f"{'Date':<12}{'Condition':<26}"
        f"{'High ' + row['unit']:>10}{'Low ' + row['unit']:>10}"
        f"{'Precip mm':>11}{'Precip %':>10}{'Wind km/h':>11}"
    )
    lines = [f"{len(row['days'])}-day forecast for {place}", "", header, "-" * len(header)]
    for day in row["days"]:
        lines.append(
            f"{day['date']:<12}{day['condition']:<26}"
            f"{day['temp_max']:>10}{day['temp_min']:>10}"
            f"{day['precipitation_sum']:>11}"
            f"{day['precipitation_probability_max']:>10}{day['windspeed_max']:>11}"
        )
    return "\n".join(lines)


def _valid_days(value):
    """argparse type for --days: an integer in [1, MAX_FORECAST_DAYS]."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--days must be an integer, got {value!r}")
    if not 1 <= n <= MAX_FORECAST_DAYS:
        raise argparse.ArgumentTypeError(
            f"--days must be between 1 and {MAX_FORECAST_DAYS}, got {n}"
        )
    return n


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Look up the multi-day weather forecast for a named location."
    )
    parser.add_argument(
        "location",
        help='Location name, e.g. "London", "New York", "Tokyo"',
    )
    parser.add_argument(
        "--days",
        type=_valid_days,
        default=DEFAULT_FORECAST_DAYS,
        help=f"Number of forecast days, 1-{MAX_FORECAST_DAYS} (default: {DEFAULT_FORECAST_DAYS})",
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
        print(f"Looking up the {args.days}-day forecast for '{args.location}'...\n")

    try:
        row = get_forecast(args.location, days=args.days, unit=args.unit)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    if row is None:
        die(f"No location found matching '{args.location}'.", args.json)

    if args.json:
        print(json.dumps(row, indent=2))
        return

    print(format_forecast(row))


if __name__ == "__main__":
    main()
