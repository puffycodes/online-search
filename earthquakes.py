#!/usr/bin/env python3
"""
List recent earthquakes near a named location, from the USGS earthquake
catalog (ComCat, https://earthquake.usgs.gov/fdsnws/event/1/), within a
radius of the place Open-Meteo's geocoding finds for the name.

No API key required. USGS data is US-government public domain; USGS asks
to be credited, so every result ends with ATTRIBUTION (which also credits
Open-Meteo for the place lookup).

Defaults: within 300 km, magnitude 2.5 and up, over the last 30 days,
newest first, at most 20 quakes; --radius, --min-magnitude, --days (or
--start / --end), --order and --limit change them. Outside the US the
catalog has few quakes below about magnitude 4.5, so a quiet result there
doesn't mean no small quakes happened: such results carry a
``coverage_note``.

Requires weather.py (in this same directory) for geocoding - imported
directly rather than shelling out.

Supports a --json flag for structured output, so this script can be
called as a tool by an agent: it parses stdout instead of a human-
readable report.
"""

import argparse
import datetime as dt
import json
import math

import requests

import daily_prices
from cli_utils import bounded_int, die, positive_int, use_utf8_output
from weather import ATTRIBUTION as OPEN_METEO_ATTRIBUTION
from weather import REQUEST_TIMEOUT, format_place, geocode, place_fields

QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
EVENT_PAGE_URL = "https://earthquake.usgs.gov/earthquakes/eventpage/"
# USGS asks to be credited (https://www.usgs.gov/information-policies-and-instructions/crediting-usgs);
# the place lookup is Open-Meteo's, whose CC BY 4.0 licence requires its own credit.
ATTRIBUTION = (
    "Earthquake data courtesy of the U.S. Geological Survey (https://earthquake.usgs.gov/). "
    f"Place lookup: {OPEN_METEO_ATTRIBUTION}"
)

DEFAULT_RADIUS_KM = 300
DEFAULT_MIN_MAGNITUDE = 2.5
DEFAULT_DAYS = 30
DEFAULT_LIMIT = 20
# The API's own caps: a circle up to half the Earth's circumference, and at
# most 20,000 events per query (more is a 400).
MAX_RADIUS_KM = 20000
MAX_LIMIT = 20000
EARTH_RADIUS_KM = 6371.0

COVERAGE_NOTE = (
    "Outside the US the USGS catalog lists few earthquakes below about magnitude 4.5, "
    "so smaller quakes there are mostly missing, not absent."
)


def fetch_geojson(params):
    """GET the event query as GeoJSON and return the parsed body.

    A rejected query comes back as plain text ("Error 400: Bad Request",
    a blank line, then the reason); raise that reason rather than a bare
    "400 Client Error". 204 No Content is read as no events.
    """
    response = requests.get(QUERY_URL, params={"format": "geojson", **params},
                            timeout=REQUEST_TIMEOUT)
    if response.status_code == 204:
        return {"features": []}
    if not response.ok:
        lines = [line.strip() for line in response.text.splitlines() if line.strip()]
        if len(lines) > 1 and lines[0].startswith("Error"):
            raise requests.HTTPError(f"{response.status_code}: {lines[1]}", response=response)
    response.raise_for_status()
    return response.json()


def resolve_window(days=None, start=None, end=None, today=None):
    """The inclusive ``(first, final)`` UTC dates to search.

    ``start`` (and ``end``, default today) wins; otherwise the last ``days``
    calendar days ending today (DEFAULT_DAYS when not given), so 1 is today. Raises ``ValueError``
    for a malformed date, ``end`` without ``start``, or an end before the
    start.
    """
    today = today or dt.datetime.now(dt.timezone.utc).date()
    if start or end:
        return daily_prices.resolve_window(start, end, today=today)
    return today - dt.timedelta(days=(days or DEFAULT_DAYS) - 1), today


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, in km (haversine)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def utc_time(millis):
    """Epoch milliseconds as an ISO UTC timestamp ("2026-10-26T12:34:56Z")."""
    if millis is None:
        return None
    moment = dt.datetime.fromtimestamp(millis / 1000, tz=dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def quake_row(feature, latitude, longitude):
    """One GeoJSON feature as a flat record, with its distance from the place."""
    props = feature.get("properties") or {}
    coords = (feature.get("geometry") or {}).get("coordinates") or [None, None, None]
    lon, lat, depth = (list(coords) + [None, None, None])[:3]
    return {
        "time": utc_time(props.get("time")),
        "magnitude": props.get("mag"),
        "magnitude_type": props.get("magType"),
        "place": props.get("place"),
        "latitude": lat,
        "longitude": lon,
        "depth_km": round(depth, 1) if depth is not None else None,
        "distance_km": (round(distance_km(latitude, longitude, lat, lon))
                        if lat is not None and lon is not None else None),
        "status": props.get("status"),
        "tsunami": bool(props.get("tsunami")),
        "alert": props.get("alert"),
        "felt": props.get("felt"),
        "url": props.get("url") or (EVENT_PAGE_URL + feature["id"] if feature.get("id") else None),
    }


def get_earthquakes(location, radius_km=DEFAULT_RADIUS_KM, min_magnitude=DEFAULT_MIN_MAGNITUDE,
                    first=None, final=None, order="time", limit=DEFAULT_LIMIT):
    """Look up a location and return the earthquakes around it as a dict,
    or None if the location can't be found.

    ``first`` / ``final`` are inclusive UTC dates (default: the last
    DEFAULT_DAYS days). One more quake than ``limit`` is asked for, so
    ``more`` can say whether the list was cut short.
    """
    place = geocode(location)
    if place is None:
        return None
    if first is None or final is None:
        first, final = resolve_window()

    latitude, longitude = place["latitude"], place["longitude"]
    data = fetch_geojson({
        "latitude": latitude,
        "longitude": longitude,
        "maxradiuskm": radius_km,
        "minmagnitude": min_magnitude,
        "starttime": first.isoformat(),
        # endtime is a moment, so the day after the final date makes it inclusive.
        "endtime": (final + dt.timedelta(days=1)).isoformat(),
        "orderby": order,
        "limit": limit + 1,
    })
    features = data.get("features") or []
    quakes = [quake_row(feature, latitude, longitude) for feature in features[:limit]]

    row = {
        **place_fields(place),
        "radius_km": radius_km,
        "min_magnitude": min_magnitude,
        "start": first.isoformat(),
        "end": final.isoformat(),
        "order": order,
        "limit": limit,
        "count": len(quakes),
        "more": len(features) > limit,
        "earthquakes": quakes,
    }
    if place.get("country_code") != "US":
        row["coverage_note"] = COVERAGE_NOTE
    return row


def format_earthquakes(row):
    """Render a get_earthquakes() record as a human-readable report."""
    order = "newest first" if row["order"] == "time" else "largest first"
    lines = [
        f"Earthquakes within {row['radius_km']} km of {format_place(row)}",
        f"Magnitude {row['min_magnitude']:g}+, {row['start']} to {row['end']} (UTC), {order}",
        "",
    ]
    if not row["earthquakes"]:
        lines.append("No earthquakes found.")
    else:
        header = f"{'Time (UTC)':<22}{'Mag':>5}  {'Depth':>8}  {'Away':>8}  Place"
        lines += [header, "-" * len(header)]
        for quake in row["earthquakes"]:
            mag = f"{quake['magnitude']:.1f}" if quake["magnitude"] is not None else "-"
            depth = f"{quake['depth_km']:g} km" if quake["depth_km"] is not None else "-"
            away = f"{quake['distance_km']} km" if quake["distance_km"] is not None else "-"
            flags = []
            if quake["tsunami"]:
                flags.append("tsunami flag")
            if quake["alert"]:
                flags.append(f"PAGER {quake['alert']}")
            if quake["status"] == "automatic":
                flags.append("not yet reviewed")
            extra = f"  [{', '.join(flags)}]" if flags else ""
            lines.append(f"{quake['time'] or '-':<22}{mag:>5}  {depth:>8}  {away:>8}  "
                         f"{quake['place'] or '-'}{extra}")
        if row["more"]:
            lines += ["", f"More earthquakes match; showing the first {row['limit']} "
                          f"(raise --limit to see more)."]
    if row.get("coverage_note"):
        lines += ["", f"Note: {row['coverage_note']}"]
    return "\n".join(lines)


def magnitude(value):
    """argparse ``type`` for a magnitude: any number from -2 to 10."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}")
    if not -2 <= number <= 10:
        raise argparse.ArgumentTypeError(f"must be from -2 to 10, got {number:g}")
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="List recent earthquakes near a named location, from the USGS catalog."
    )
    parser.add_argument(
        "location",
        help='Location name, e.g. "Tokyo", "San Francisco", "Anchorage, Alaska"',
    )
    parser.add_argument(
        "--radius",
        type=bounded_int(MAX_RADIUS_KM),
        default=DEFAULT_RADIUS_KM,
        metavar="KM",
        help=f"Search radius around the place in km (default: {DEFAULT_RADIUS_KM}, "
             f"at most {MAX_RADIUS_KM})",
    )
    parser.add_argument(
        "--min-magnitude",
        type=magnitude,
        default=DEFAULT_MIN_MAGNITUDE,
        metavar="M",
        help=f"Smallest magnitude to list (default: {DEFAULT_MIN_MAGNITUDE:g})",
    )
    window = parser.add_mutually_exclusive_group()
    window.add_argument(
        "--days",
        type=positive_int,
        metavar="N",
        help=f"The last N days, ending today (UTC); 1 is today (default: {DEFAULT_DAYS})",
    )
    window.add_argument("--start", help="Start date YYYY-MM-DD, UTC (with optional --end)")
    parser.add_argument("--end", help="End date YYYY-MM-DD, UTC, inclusive (defaults to today)")
    parser.add_argument(
        "--order",
        choices=["time", "magnitude"],
        default="time",
        help="List newest first (time, the default) or largest first (magnitude)",
    )
    parser.add_argument(
        "--limit",
        type=bounded_int(MAX_LIMIT),
        default=DEFAULT_LIMIT,
        metavar="N",
        help=f"Most earthquakes to list (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON on stdout instead of a human-readable report.",
    )
    args = parser.parse_args(argv)
    if args.end and not args.start:
        parser.error("--end requires --start")
    return args


def main(argv=None):
    use_utf8_output()
    args = parse_args(argv)

    try:
        first, final = resolve_window(args.days, args.start, args.end)
    except ValueError as exc:
        die(str(exc), args.json)

    if not args.json:
        print(f"Looking up earthquakes near '{args.location}'...\n")

    try:
        row = get_earthquakes(args.location, radius_km=args.radius,
                              min_magnitude=args.min_magnitude, first=first, final=final,
                              order=args.order, limit=args.limit)
    except requests.RequestException as exc:
        die(str(exc), args.json)

    if row is None:
        die(f"No location found matching '{args.location}'.", args.json)

    row["attribution"] = ATTRIBUTION
    if args.json:
        print(json.dumps(row, indent=2))
        return

    print(format_earthquakes(row))
    print(f"\n{ATTRIBUTION}")


if __name__ == "__main__":
    main()
