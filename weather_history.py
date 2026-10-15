#!/usr/bin/env python3
"""
Look up the past weather for a named location on a date or over a date
range, using Open-Meteo's public geocoding and historical-weather (archive)
APIs (https://open-meteo.com/en/docs/historical-weather-api).

No API key required.

Each day carries the condition, high/low/mean temperature, precipitation
(rain and snowfall), maximum wind, and sunrise, sunset and daylight hours in
the location's local time. A range of more than one day also gets a summary:
average high and low, the warmest and coldest day, total precipitation and
the number of wet days. Data starts on 1940-01-01; the most recent days come
from a reanalysis model that is revised for about a week afterwards.

Requires weather.py (in this same directory) for geocoding, the HTTP call
and weather-code descriptions — imported directly rather than shelling out.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import datetime as dt
import json

import requests

from cli_utils import die, positive_int, use_utf8_output
from weather import (
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

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
EARLIEST_DATE = dt.date(1940, 1, 1)  # the archive's first day
MAX_RANGE_DAYS = 366
WET_DAY_MM = 1.0  # the usual climatological threshold for a "wet day"

DAILY_FIELDS = ",".join(
    [
        "weathercode",
        "temperature_2m_max",
        "temperature_2m_min",
        "temperature_2m_mean",
        "precipitation_sum",
        "rain_sum",
        "snowfall_sum",
        "windspeed_10m_max",
        "sunrise",
        "sunset",
        "daylight_duration",
    ]
)


def fetch_daily_history(latitude, longitude, start, end, unit="celsius"):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": DAILY_FIELDS,
        # "auto" resolves each location's own local timezone, so daily
        # buckets line up with its calendar days rather than UTC's.
        "timezone": "auto",
        "temperature_unit": unit,
    }
    data = fetch_json(ARCHIVE_URL, params)
    return data.get("daily") or {}


def build_day(daily, i):
    code = daily_value(daily, "weathercode", i)
    return {
        "date": daily["time"][i],
        "weather_code": code,
        "condition": None if code is None else weather_description(code),
        "temp_max": daily_value(daily, "temperature_2m_max", i),
        "temp_min": daily_value(daily, "temperature_2m_min", i),
        "temp_mean": daily_value(daily, "temperature_2m_mean", i),
        "precipitation_sum": daily_value(daily, "precipitation_sum", i),
        "rain_sum": daily_value(daily, "rain_sum", i),
        "snowfall_sum": daily_value(daily, "snowfall_sum", i),
        "windspeed_max": daily_value(daily, "windspeed_10m_max", i),
        **sun_fields(daily, i),
    }


def summarize(days):
    """Aggregate a list of day records; None for a single day or no data.

    Days with a missing value are left out of that value's figure, so a
    partial last day doesn't drag the averages; ``days_with_data`` counts
    the days that had a high temperature.
    """
    if len(days) < 2:
        return None

    def present(key):
        return [d for d in days if d[key] is not None]

    highs, lows = present("temp_max"), present("temp_min")
    precip, snow = present("precipitation_sum"), present("snowfall_sum")
    if not highs and not lows and not precip:
        return None

    def average(rows, key):
        return round(sum(r[key] for r in rows) / len(rows), 1) if rows else None

    warmest = max(highs, key=lambda d: d["temp_max"]) if highs else None
    coldest = min(lows, key=lambda d: d["temp_min"]) if lows else None
    return {
        "days": len(days),
        "days_with_data": len(highs),
        "avg_temp_max": average(highs, "temp_max"),
        "avg_temp_min": average(lows, "temp_min"),
        "warmest": warmest and {"date": warmest["date"], "temp_max": warmest["temp_max"]},
        "coldest": coldest and {"date": coldest["date"], "temp_min": coldest["temp_min"]},
        "total_precipitation": round(sum(d["precipitation_sum"] for d in precip), 1) if precip else None,
        "wet_days": sum(1 for d in precip if d["precipitation_sum"] >= WET_DAY_MM) if precip else None,
        "total_snowfall": round(sum(d["snowfall_sum"] for d in snow), 1) if snow else None,
    }


def get_history(location, start, end, unit="celsius"):
    """Look up a location and return its daily weather from ``start`` to
    ``end`` (dates, inclusive) as a dict, or None if the location can't be
    found."""
    place = geocode(location)
    if place is None:
        return None

    daily = fetch_daily_history(place["latitude"], place["longitude"], start, end, unit=unit)
    days = [build_day(daily, i) for i in range(len(daily.get("time") or []))]
    return {
        **place_fields(place),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "unit": "°C" if unit == "celsius" else "°F",
        "days": days,
        "summary": summarize(days),
    }


def _cell(value, width, fmt="{}"):
    return f"{'-' if value is None else fmt.format(value):>{width}}"


def format_history(row):
    """Render a get_history() record as a human-readable table plus summary."""
    place = format_place(row)
    unit = row["unit"]
    if row["start_date"] == row["end_date"]:
        title = f"Weather for {place} on {row['start_date']}"
    else:
        title = f"Weather for {place}, {row['start_date']} to {row['end_date']}"

    header = (
        f"{'Date':<12}{'Condition':<26}"
        f"{'High ' + unit:>9}{'Low ' + unit:>9}{'Mean ' + unit:>9}"
        f"{'Precip mm':>11}{'Snow cm':>9}{'Wind km/h':>11}"
        f"{'Sunrise':>13}{'Sunset':>8}{'Daylight':>10}"
    )
    lines = [title, "", header, "-" * len(header)]
    for day in row["days"]:
        sunrise, sunset = format_sun(day)
        lines.append(
            f"{day['date']:<12}{day['condition'] or '-':<26}"
            f"{_cell(day['temp_max'], 9)}{_cell(day['temp_min'], 9)}{_cell(day['temp_mean'], 9)}"
            f"{_cell(day['precipitation_sum'], 11)}{_cell(day['snowfall_sum'], 9)}"
            f"{_cell(day['windspeed_max'], 11)}"
            f"{sunrise:>13}{sunset:>8}{format_daylight(day['daylight_hours']):>10}"
        )

    summary = row["summary"]
    if summary:
        lines += ["", f"Summary ({summary['days']} days)"]
        lines.append(
            f"  Average high / low   {_cell(summary['avg_temp_max'], 0)}{unit} / "
            f"{_cell(summary['avg_temp_min'], 0)}{unit}"
        )
        if summary["warmest"]:
            lines.append(
                f"  Warmest day          {summary['warmest']['temp_max']}{unit} on {summary['warmest']['date']}"
            )
        if summary["coldest"]:
            lines.append(
                f"  Coldest night        {summary['coldest']['temp_min']}{unit} on {summary['coldest']['date']}"
            )
        if summary["total_precipitation"] is not None:
            lines.append(
                f"  Total precipitation  {summary['total_precipitation']} mm "
                f"({summary['wet_days']} wet days, >= {WET_DAY_MM:g} mm)"
            )
        if summary["total_snowfall"]:
            lines.append(f"  Total snowfall       {summary['total_snowfall']} cm")
        if summary["days_with_data"] < summary["days"]:
            lines.append(
                f"  ({summary['days'] - summary['days_with_data']} day(s) have no data yet)"
            )
    return "\n".join(lines)


def _date(value):
    """argparse type for a YYYY-MM-DD date."""
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}, expected YYYY-MM-DD")


def resolve_window(args, parser, today=None):
    """Turn --date / --start / --end / --last into a (start, end) pair of
    dates, calling ``parser.error`` (exit 2) for a missing, reversed,
    out-of-range or over-long window.

    ``--last N`` is the N full days ending yesterday; today is left out
    because its figures are still partial."""
    today = today or dt.date.today()
    if args.last:
        if args.date or args.start or args.end:
            parser.error("--last cannot be combined with --date/--start/--end")
        end = today - dt.timedelta(days=1)
        start = end - dt.timedelta(days=args.last - 1)
    elif args.date:
        if args.start or args.end:
            parser.error("--date cannot be combined with --start/--end")
        start = end = args.date
    elif args.start:
        start, end = args.start, args.end or today
    elif args.end:
        parser.error("--end requires --start")
    else:
        parser.error("give a --date, a --start (with optional --end), or --last N")

    if end < start:
        parser.error("--end must not be before --start")
    if start < EARLIEST_DATE:
        parser.error(f"historical data starts on {EARLIEST_DATE.isoformat()}")
    if end > today:
        parser.error(
            f"{end.isoformat()} is in the future; use weather_forecast.py for upcoming days"
        )
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        parser.error(f"the range is limited to {MAX_RANGE_DAYS} days; narrow the window")
    return start, end


def parse_args(argv=None, today=None):
    parser = argparse.ArgumentParser(
        description="Look up the past weather for a named location on a date or over a date range."
    )
    parser.add_argument(
        "location",
        help='Location name, e.g. "London", "New York", "Tokyo"',
    )
    parser.add_argument("--date", type=_date, help="A single day, YYYY-MM-DD")
    parser.add_argument("--start", type=_date, help="First day of a range, YYYY-MM-DD")
    parser.add_argument(
        "--end", type=_date, help="Last day of a range, YYYY-MM-DD (default: today)"
    )
    parser.add_argument(
        "--last",
        type=positive_int,
        metavar="N",
        help="The last N full days, ending yesterday (today's figures are partial)",
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
    args = parser.parse_args(argv)
    args.start, args.end = resolve_window(args, parser, today)
    return args


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    if not args.json:
        span = (
            args.start.isoformat()
            if args.start == args.end
            else f"{args.start.isoformat()} to {args.end.isoformat()}"
        )
        print(f"Looking up the weather for '{args.location}' on {span}...\n")

    try:
        row = get_history(args.location, args.start, args.end, unit=args.unit)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    if row is None:
        die(f"No location found matching '{args.location}'.", args.json)

    if args.json:
        print(json.dumps(row, indent=2))
        return

    print(format_history(row))


if __name__ == "__main__":
    main()
