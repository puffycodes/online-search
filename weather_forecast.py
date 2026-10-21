#!/usr/bin/env python3
"""
Look up the multi-day weather forecast for a named location, using
Open-Meteo's public geocoding and forecast APIs (https://open-meteo.com/).
Each day carries the condition, high/low, precipitation and wind, plus the
maximum UV index (with its WHO category), sunrise, sunset and daylight hours
in the location's local time.

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

from cli_utils import die, use_utf8_output
from weather import (
    ATTRIBUTION,
    FORECAST_URL,
    daily_value,
    fetch_json,
    format_daylight,
    format_place,
    format_sun,
    geocode,
    place_fields,
    sun_fields,
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
        "uv_index_max",
        "sunrise",
        "sunset",
        "daylight_duration",
    ]
)

# WHO UV index categories: (lower bound, label), highest first.
UV_CATEGORIES = [(11, "Extreme"), (8, "Very high"), (6, "High"), (3, "Moderate"), (0, "Low")]


def uv_category(uv):
    """The WHO category for a daily maximum UV index, or None if missing.

    Bands are 0-2 Low, 3-5 Moderate, 6-7 High, 8-10 Very high, 11+ Extreme;
    the index is rounded half up first, as the WHO scale uses whole numbers
    (Python's round() would send 2.5 to 2).
    """
    if uv is None:
        return None
    value = int(uv + 0.5)
    return next(label for bound, label in UV_CATEGORIES if value >= bound)


def fetch_daily_forecast(latitude, longitude, days=DEFAULT_FORECAST_DAYS, unit="celsius",
                         start=None, end=None):
    """The ``daily`` block of the forecast: ``days`` days from today, or,
    given ``start`` and ``end`` (dates, inclusive, within the 16-day
    horizon), just that window (trip_weather.py uses it)."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": DAILY_FIELDS,
        # "auto" resolves each location's own local timezone, so daily
        # buckets line up with its calendar days rather than UTC's.
        "timezone": "auto",
        "temperature_unit": unit,
    }
    if start is not None and end is not None:
        params["start_date"] = start.isoformat()
        params["end_date"] = end.isoformat()
    else:
        params["forecast_days"] = days
    data = fetch_json(FORECAST_URL, params)
    return data.get("daily") or {}


def forecast_day(daily, i):
    """Day ``i`` of a fetch_daily_forecast() block as a day record."""
    return {
        "date": daily["time"][i],
        "weather_code": daily["weathercode"][i],
        "condition": weather_description(daily["weathercode"][i]),
        "temp_max": daily["temperature_2m_max"][i],
        "temp_min": daily["temperature_2m_min"][i],
        "precipitation_sum": daily["precipitation_sum"][i],
        "precipitation_probability_max": daily["precipitation_probability_max"][i],
        "windspeed_max": daily["windspeed_10m_max"][i],
        "uv_index_max": daily_value(daily, "uv_index_max", i),
        "uv_category": uv_category(daily_value(daily, "uv_index_max", i)),
        **sun_fields(daily, i),
    }


def get_forecast(location, days=DEFAULT_FORECAST_DAYS, unit="celsius"):
    """Look up a location and return its multi-day forecast as a dict,
    or None if the location can't be found."""
    place = geocode(location)
    if place is None:
        return None

    daily = fetch_daily_forecast(place["latitude"], place["longitude"], days=days, unit=unit)
    forecast_days = [forecast_day(daily, i) for i in range(len(daily.get("time", [])))]

    return {
        **place_fields(place),
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

    sun_header = (
        f"{'Date':<12}{'UV max':>8}  {'UV level':<11}"
        f"{'Sunrise':>13}{'Sunset':>8}{'Daylight':>10}"
    )
    lines += ["", sun_header, "-" * len(sun_header)]
    for day in row["days"]:
        uv = "-" if day["uv_index_max"] is None else f"{day['uv_index_max']:.1f}"
        sunrise, sunset = format_sun(day)
        lines.append(
            f"{day['date']:<12}{uv:>8}  {day['uv_category'] or '-':<11}"
            f"{sunrise:>13}{sunset:>8}{format_daylight(day['daylight_hours']):>10}"
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
    use_utf8_output()
    args = parse_args(argv)

    if not args.json:
        print(f"Looking up the {args.days}-day forecast for '{args.location}'...\n")

    try:
        row = get_forecast(args.location, days=args.days, unit=args.unit)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    if row is None:
        die(f"No location found matching '{args.location}'.", args.json)

    row["attribution"] = ATTRIBUTION
    if args.json:
        print(json.dumps(row, indent=2))
        return

    print(format_forecast(row))
    print(f"\n{ATTRIBUTION}")


if __name__ == "__main__":
    main()
