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

from cli_utils import die, use_utf8_output

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 10
SECONDS_PER_DAY = 86400
# Open-Meteo's data is CC-BY 4.0, which requires this credit on every result
# (https://open-meteo.com/en/terms). Shared by all four Open-Meteo scripts.
ATTRIBUTION = "Data by Open-Meteo.com (https://open-meteo.com/), licensed under CC BY 4.0."

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
    if not response.ok:
        # Open-Meteo explains a rejected request as {"error": true, "reason": "..."};
        # surface that rather than a bare "400 Client Error".
        try:
            reason = response.json().get("reason")
        except (ValueError, AttributeError):
            reason = None
        if reason:
            raise requests.HTTPError(f"{response.status_code}: {reason}", response=response)
    response.raise_for_status()
    return response.json()


def daily_value(daily, key, i):
    """Day ``i`` of an Open-Meteo ``daily`` block's ``key`` series, or None."""
    values = daily.get(key) or []
    return values[i] if i < len(values) else None


def sun_fields(daily, i):
    """Sunrise, sunset and daylight for day ``i`` of an Open-Meteo ``daily``
    block requested with sunrise, sunset and daylight_duration. Times are
    the location's local "HH:MM" (the API is called with timezone=auto);
    daylight is in hours. Shared by weather_forecast.py and weather_history.py.

    In polar night (0 h of daylight) and midnight sun (24 h) Open-Meteo
    reports sunrise and sunset as midnight placeholders, so both become None
    and ``polar`` says which it is ("night" / "day"; None otherwise).
    """
    def clock(value):
        return value.split("T", 1)[1] if value and "T" in value else None

    seconds = daily_value(daily, "daylight_duration", i)
    polar = None
    if seconds is not None and seconds <= 0:
        polar = "night"
    elif seconds is not None and seconds >= SECONDS_PER_DAY:
        polar = "day"
    return {
        "sunrise": None if polar else clock(daily_value(daily, "sunrise", i)),
        "sunset": None if polar else clock(daily_value(daily, "sunset", i)),
        "daylight_hours": None if seconds is None else round(seconds / 3600, 2),
        "polar": polar,
    }


def format_sun(day):
    """(sunrise, sunset) display strings for a record carrying sun_fields():
    "HH:MM", "polar night" / "midnight sun" (sunset left blank), or "-"."""
    if day.get("polar") == "night":
        return "polar night", ""
    if day.get("polar") == "day":
        return "midnight sun", ""
    return day.get("sunrise") or "-", day.get("sunset") or "-"


def format_daylight(hours):
    """Daylight hours as "12h05m", or "-" when missing."""
    if hours is None:
        return "-"
    minutes = round(hours * 60)
    return f"{minutes // 60}h{minutes % 60:02d}m"


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


def place_fields(place):
    """The location fields every record built from a geocode() match starts
    with: location, admin1, country, latitude, longitude. Shared by
    get_weather() here, get_forecast() in weather_forecast.py,
    get_history() in weather_history.py and get_air_quality() in
    air_quality.py."""
    return {
        "location": place.get("name"),
        "admin1": place.get("admin1"),
        "country": place.get("country"),
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
    }


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
        **place_fields(place),
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
    use_utf8_output()
    args = parse_args(argv)

    if not args.json:
        print(f"Looking up the weather for '{args.location}'...\n")

    try:
        row = get_weather(args.location, unit=args.unit)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    if row is None:
        die(f"No location found matching '{args.location}'.", args.json)

    row["attribution"] = ATTRIBUTION
    if args.json:
        print(json.dumps(row, indent=2))
        return

    print(format_weather(row))
    print(f"\n{ATTRIBUTION}")


if __name__ == "__main__":
    main()
