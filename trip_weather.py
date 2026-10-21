#!/usr/bin/env python3
"""
Weather for a trip: one place, a range of dates, everything the other
Open-Meteo scripts know about those days, merged by date.

- Days within the 16-day forecast get the forecast from
  weather_forecast.py: condition, high / low, precipitation and its chance,
  wind, UV index, sunrise, sunset and daylight.
- Days further ahead get typical weather instead: the same calendar dates
  in each of the last --years years (default 5) from weather_history.py's
  archive, averaged - high, low, their range over those years, precipitation,
  how many of those years were wet that day, and last year's sunrise and
  sunset. This is history, not a forecast, and is labelled so everywhere.
- Days within the air-quality forecast (values run about 4-5 days ahead,
  pollen about 3 and only in Europe) get the day's worst hour from
  air_quality.py: US AQI with its category, European AQI, and pollen.

The place is looked up once with weather.py's geocoding. Trips run from
yesterday (to allow for time zones) up to a year ahead, at most 31 days
long.

No API key required. Open-Meteo's data is CC BY 4.0, so every result ends
with weather.ATTRIBUTION.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import datetime as dt
import json

import requests

import air_quality
import weather_forecast
import weather_history
from cli_utils import die, use_utf8_output
from weather import ATTRIBUTION, format_daylight, format_place, format_sun, geocode, place_fields

MAX_TRIP_DAYS = 31
MAX_DAYS_AHEAD = 366
DEFAULT_YEARS = 5
MAX_YEARS = 20
# Forecast days run from today to today + 15 (weather_forecast.MAX_FORECAST_DAYS).
FORECAST_DAYS = weather_forecast.MAX_FORECAST_DAYS
WET_DAY_MM = weather_history.WET_DAY_MM


def today_utc():
    return dt.datetime.now(dt.timezone.utc).date()


def shift_year(date, years):
    """``date`` moved by ``years`` years; 29 February becomes the 28th in a
    non-leap year."""
    try:
        return date.replace(year=date.year + years)
    except ValueError:
        return date.replace(year=date.year + years, day=28)


def date_range(start, end):
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


def forecast_records(latitude, longitude, dates, unit):
    """Forecast day records for ``dates`` (consecutive, within the horizon).

    A day the forecast returns without a condition or temperatures (seen
    on the 16th day) is left out, so the caller gives it typical weather.
    """
    daily = weather_forecast.fetch_daily_forecast(
        latitude, longitude, unit=unit, start=dates[0], end=dates[-1]
    )
    codes = daily.get("weathercode") or []
    highs = daily.get("temperature_2m_max") or []
    return [
        dict(weather_forecast.forecast_day(daily, i), source="forecast")
        for i in range(len(daily.get("time") or []))
        if (i < len(codes) and codes[i] is not None) or (i < len(highs) and highs[i] is not None)
    ]


def typical_record(date, samples):
    """One trip date's typical weather from ``samples``: the archive's day
    records for the same date in past years, most recent first."""
    def values(key):
        return [s[key] for s in samples if s[key] is not None]

    def average(key):
        found = values(key)
        return round(sum(found) / len(found), 1) if found else None

    def spread(key):
        found = values(key)
        return [min(found), max(found)] if found else None

    precip = values("precipitation_sum")
    latest = samples[0] if samples else {}
    return {
        "date": date.isoformat(),
        "source": "typical",
        "years": len(samples),
        "temp_max": average("temp_max"),
        "temp_min": average("temp_min"),
        "temp_max_range": spread("temp_max"),
        "temp_min_range": spread("temp_min"),
        "precipitation_sum": average("precipitation_sum"),
        "wet_years": sum(1 for p in precip if p >= WET_DAY_MM) if precip else None,
        "snowfall_sum": average("snowfall_sum"),
        # Sun times barely move from year to year; last year's stand in.
        "sunrise": latest.get("sunrise"),
        "sunset": latest.get("sunset"),
        "daylight_hours": latest.get("daylight_hours"),
        "polar": latest.get("polar"),
    }


def typical_records(latitude, longitude, dates, years, unit):
    """Typical-weather records for ``dates``, from the same dates in each
    of the last ``years`` years before the trip (one archive request per
    year). Returns (records, [first year, last year])."""
    by_back = {}
    for back in range(1, years + 1):
        daily = weather_history.fetch_daily_history(
            latitude, longitude, shift_year(dates[0], -back), shift_year(dates[-1], -back), unit=unit
        )
        by_back[back] = {
            day["date"]: day
            for day in (weather_history.build_day(daily, i) for i in range(len(daily.get("time") or [])))
        }
    records = []
    for date in dates:
        samples = [
            by_back[back][key]
            for back in range(1, years + 1)
            if (key := shift_year(date, -back).isoformat()) in by_back[back]
        ]
        records.append(typical_record(date, samples))
    trip_year = dates[0].year
    return records, [trip_year - years, trip_year - 1]


def get_trip_weather(location, start, end, years=DEFAULT_YEARS, unit="celsius", today=None):
    """Look up ``location`` and return the trip record for ``start``..``end``
    (dates, inclusive), or None if the location can't be found."""
    place = geocode(location)
    if place is None:
        return None
    today = today or today_utc()
    latitude, longitude = place["latitude"], place["longitude"]
    dates = date_range(start, end)
    last_forecast = today + dt.timedelta(days=FORECAST_DAYS - 1)

    forecast_dates = [d for d in dates if d <= last_forecast]
    days = forecast_records(latitude, longitude, forecast_dates, unit) if forecast_dates else []
    covered = {day["date"] for day in days}
    typical_dates = [d for d in dates if d.isoformat() not in covered]
    typical_years = None
    if typical_dates:
        typical, typical_years = typical_records(latitude, longitude, typical_dates, years, unit)
        days = sorted(days + typical, key=lambda day: day["date"])

    last_air = today + dt.timedelta(days=air_quality.MAX_FORECAST_DAYS - 1)
    air = {}
    if start <= last_air:
        hourly = air_quality.fetch_hourly_air_quality(latitude, longitude, start, min(end, last_air))
        air = air_quality.daily_maxima(hourly)
    for day in days:
        day["air"] = air.get(day["date"])

    notes = []
    if typical_dates:
        notes.append(
            f"{typical_dates[0]} onwards is beyond the forecast: typical weather "
            f"for those dates in {typical_years[0]}-{typical_years[1]}, not a forecast."
        )
    if any(day["air"] is None for day in days):
        notes.append(
            "Air quality is only forecast about 4-5 days ahead (pollen about 3, and only in Europe); "
            "later days have none."
        )
    return {
        **place_fields(place),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "unit": "°C" if unit == "celsius" else "°F",
        "typical_years": typical_years,
        "days": days,
        "summary": summarize(days),
        "notes": notes,
    }


def summarize(days):
    """Counts by source, and the trip's highest and lowest temperatures."""
    highs = [d for d in days if d["temp_max"] is not None]
    lows = [d for d in days if d["temp_min"] is not None]
    highest = max(highs, key=lambda d: d["temp_max"]) if highs else None
    lowest = min(lows, key=lambda d: d["temp_min"]) if lows else None
    forecast = [d for d in days if d["source"] == "forecast"]
    return {
        "forecast_days": len(forecast),
        "typical_days": len(days) - len(forecast),
        "air_quality_days": sum(1 for d in days if d["air"]),
        "forecast_wet_days": sum(
            1 for d in forecast if (d["precipitation_sum"] or 0) >= WET_DAY_MM
        ),
        "highest": highest and {"date": highest["date"], "temp_max": highest["temp_max"],
                                "source": highest["source"]},
        "lowest": lowest and {"date": lowest["date"], "temp_min": lowest["temp_min"],
                              "source": lowest["source"]},
    }


def _cell(value, width, fmt="{}"):
    return f"{'-' if value is None else fmt.format(value):>{width}}"


def _sun_cells(day):
    sunrise, sunset = format_sun(day)
    return f"{sunrise:>13}{sunset:>8}{format_daylight(day['daylight_hours']):>10}"


def format_pollen(air):
    """The day's pollen as "birch 3.2, grass 1.0", "none" or "-" (no data)."""
    counts = [(plant, air.get(f"{plant}_pollen")) for plant in air_quality.POLLEN_TYPES]
    known = [(plant, value) for plant, value in counts if value is not None]
    if not known:
        return "-"
    present = [f"{plant} {value:g}" for plant, value in known if value > 0]
    return ", ".join(present) if present else "none"


def format_trip(row):
    """Render a get_trip_weather() record as a human-readable report."""
    unit = row["unit"]
    lines = [
        f"Trip weather for {format_place(row)}, {row['start_date']} to {row['end_date']}",
    ]
    forecast = [d for d in row["days"] if d["source"] == "forecast"]
    typical = [d for d in row["days"] if d["source"] == "typical"]

    if forecast:
        header = (
            f"{'Date':<12}{'Condition':<26}{'High ' + unit:>9}{'Low ' + unit:>9}"
            f"{'Precip mm':>11}{'Precip %':>10}{'UV':>6}  {'UV level':<10}"
            f"{'Sunrise':>13}{'Sunset':>8}{'Daylight':>10}"
        )
        lines += ["", "Forecast", header, "-" * len(header)]
        for day in forecast:
            lines.append(
                f"{day['date']:<12}{day['condition']:<26}"
                f"{_cell(day['temp_max'], 9)}{_cell(day['temp_min'], 9)}"
                f"{_cell(day['precipitation_sum'], 11)}{_cell(day['precipitation_probability_max'], 10)}"
                f"{_cell(day['uv_index_max'], 6, '{:.1f}')}  {day['uv_category'] or '-':<10}"
                + _sun_cells(day)
            )

    if typical:
        first, last = row["typical_years"]
        header = (
            f"{'Date':<12}{'High ' + unit:>9}{'(range)':>15}{'Low ' + unit:>9}{'(range)':>15}"
            f"{'Precip mm':>11}{'Wet years':>11}{'Sunrise':>13}{'Sunset':>8}{'Daylight':>10}"
        )
        lines += ["", f"Typical weather, from the same dates in {first}-{last} (not a forecast)",
                  header, "-" * len(header)]
        for day in typical:
            def span(key):
                return "-" if day[key] is None else f"({day[key][0]} to {day[key][1]})"
            wet = "-" if day["wet_years"] is None else f"{day['wet_years']} of {day['years']}"
            lines.append(
                f"{day['date']:<12}{_cell(day['temp_max'], 9)}{span('temp_max_range'):>15}"
                f"{_cell(day['temp_min'], 9)}{span('temp_min_range'):>15}"
                f"{_cell(day['precipitation_sum'], 11)}{wet:>11}" + _sun_cells(day)
            )

    with_air = [d for d in row["days"] if d["air"]]
    if with_air:
        header = f"{'Date':<12}{'US AQI':>8}  {'Category':<32}{'EU AQI':>8}  Pollen (grains/m³)"
        lines += ["", "Air quality (the day's worst hour)", header, "-" * len(header)]
        for day in with_air:
            air = day["air"]
            partial = f"  [{air['hours']} h of forecast]" if air["hours"] < 24 else ""
            lines.append(
                f"{day['date']:<12}{_cell(air['us_aqi'], 8)}  {air['us_aqi_category'] or '-':<32}"
                f"{_cell(air['european_aqi'], 8)}  {format_pollen(air)}{partial}"
            )

    if row["notes"]:
        lines.append("")
        lines += [f"Note: {note}" for note in row["notes"]]
    return "\n".join(lines)


def _date(value):
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a date as YYYY-MM-DD, got {value!r}")


def _years(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}")
    if not 1 <= number <= MAX_YEARS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_YEARS}, got {number}")
    return number


def parse_args(argv=None, today=None):
    parser = argparse.ArgumentParser(
        description="Weather for a trip: forecast, typical weather beyond it, "
                    "UV, sun times, air quality and pollen for a place and dates."
    )
    parser.add_argument("location", help='Place name, e.g. "Paris", "Kyoto", "Cape Town"')
    parser.add_argument("--start", type=_date, required=True, help="First day of the trip, YYYY-MM-DD")
    parser.add_argument("--end", type=_date, help="Last day of the trip, YYYY-MM-DD (default: --start)")
    parser.add_argument(
        "--years",
        type=_years,
        default=DEFAULT_YEARS,
        help=f"Past years averaged for typical weather beyond the forecast "
             f"(default: {DEFAULT_YEARS}, at most {MAX_YEARS})",
    )
    parser.add_argument(
        "--unit", choices=["celsius", "fahrenheit"], default="celsius",
        help="Temperature unit (default: celsius)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    args = parser.parse_args(argv)

    today = today or today_utc()
    args.end = args.end or args.start
    if args.end < args.start:
        parser.error("--end is before --start")
    if (args.end - args.start).days + 1 > MAX_TRIP_DAYS:
        parser.error(f"a trip can be at most {MAX_TRIP_DAYS} days long")
    # Yesterday is allowed: the place's "today" may be a day behind UTC.
    if args.start < today - dt.timedelta(days=1):
        parser.error("--start is in the past; weather_history.py covers past dates")
    if args.end > today + dt.timedelta(days=MAX_DAYS_AHEAD):
        parser.error(f"the trip must end within {MAX_DAYS_AHEAD} days from today")
    return args


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    if not args.json:
        print(f"Looking up trip weather for '{args.location}', {args.start} to {args.end}...\n")

    try:
        row = get_trip_weather(args.location, args.start, args.end, years=args.years, unit=args.unit)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    if row is None:
        die(f"No location found matching '{args.location}'.", args.json)

    row["attribution"] = ATTRIBUTION
    if args.json:
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return

    print(format_trip(row))
    print(f"\n{ATTRIBUTION}")


if __name__ == "__main__":
    main()
