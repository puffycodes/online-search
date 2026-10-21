"""Tests for trip_weather: date helpers, forecast / typical / air-quality
merging, the summary, the report, argument checks and main()."""

import datetime as dt
import json

import pytest
import requests

import air_quality
import trip_weather as tw
import weather_forecast
import weather_history

TODAY = dt.date(2026, 10, 21)
PLACE = {"name": "Paris", "admin1": "Île-de-France", "country": "France",
         "latitude": 48.85, "longitude": 2.35}


def _forecast_daily(dates, empty=()):
    """A fetch_daily_forecast() block for ``dates``; days in ``empty`` are all null."""
    def col(value):
        return [None if d in empty else value for d in dates]
    return {
        "time": dates,
        "weathercode": col(3), "temperature_2m_max": col(15.0), "temperature_2m_min": col(8.0),
        "precipitation_sum": col(1.5), "precipitation_probability_max": col(60),
        "windspeed_10m_max": col(12.0), "uv_index_max": col(2.0),
        "sunrise": [f"{d}T08:00" for d in dates], "sunset": [f"{d}T18:30" for d in dates],
        "daylight_duration": [37800.0 for _ in dates],
    }


def _history_daily(dates, high):
    return {
        "time": dates, "weathercode": [61] * len(dates),
        "temperature_2m_max": [high] * len(dates), "temperature_2m_min": [high - 6] * len(dates),
        "temperature_2m_mean": [high - 3] * len(dates),
        "precipitation_sum": [2.0 if high > 12 else 0.0] * len(dates),
        "rain_sum": [0.0] * len(dates), "snowfall_sum": [0.0] * len(dates),
        "windspeed_10m_max": [10.0] * len(dates),
        "sunrise": [f"{d}T08:10" for d in dates], "sunset": [f"{d}T18:10" for d in dates],
        "daylight_duration": [36000.0] * len(dates),
    }


@pytest.fixture
def wired(monkeypatch):
    """get_trip_weather() with geocoding and the three Open-Meteo fetches faked."""
    calls = {"forecast": [], "history": [], "air": []}
    monkeypatch.setattr(tw, "geocode", lambda loc: PLACE if loc == "Paris" else None)

    def fake_forecast(lat, lon, unit="celsius", start=None, end=None, **kw):
        calls["forecast"].append((start, end, unit))
        dates = [d.isoformat() for d in tw.date_range(start, end)]
        last = (TODAY + dt.timedelta(days=15)).isoformat()
        return _forecast_daily(dates, empty={last})

    def fake_history(lat, lon, start, end, unit="celsius"):
        calls["history"].append((start, end))
        dates = [d.isoformat() for d in tw.date_range(start, end)]
        return _history_daily(dates, high=10.0 + (start.year - 2020))

    def fake_air(lat, lon, start, end):
        calls["air"].append((start, end))
        times = [f"{d}T{h:02d}:00" for d in tw.date_range(start, end) for h in range(24)]
        return {"time": times, "us_aqi": [40] * 30 + [None] * (len(times) - 30),
                "european_aqi": [30] * 30 + [None] * (len(times) - 30),
                **{f: [0.0] * 30 + [None] * (len(times) - 30) for f in air_quality.POLLEN_FIELDS}}

    monkeypatch.setattr(weather_forecast, "fetch_daily_forecast", fake_forecast)
    monkeypatch.setattr(weather_history, "fetch_daily_history", fake_history)
    monkeypatch.setattr(air_quality, "fetch_hourly_air_quality", fake_air)
    return calls


class TestShiftYear:
    def test_plain(self):
        assert tw.shift_year(dt.date(2026, 11, 6), -3) == dt.date(2023, 11, 6)

    def test_leap_day_to_non_leap_year(self):
        assert tw.shift_year(dt.date(2028, 2, 29), -1) == dt.date(2027, 2, 28)


class TestTypicalRecord:
    def test_averages_ranges_and_wet_years(self):
        samples = [
            {"temp_max": 14.0, "temp_min": 6.0, "precipitation_sum": 3.0, "snowfall_sum": 0.0,
             "sunrise": "08:45", "sunset": "18:22", "daylight_hours": 9.6, "polar": None},
            {"temp_max": 12.0, "temp_min": None, "precipitation_sum": 0.4, "snowfall_sum": 0.0,
             "sunrise": "08:44", "sunset": "18:23", "daylight_hours": 9.65, "polar": None},
        ]
        record = tw.typical_record(dt.date(2026, 11, 6), samples)
        assert record["source"] == "typical" and record["years"] == 2
        assert record["temp_max"] == 13.0 and record["temp_max_range"] == [12.0, 14.0]
        assert record["temp_min"] == 6.0 and record["temp_min_range"] == [6.0, 6.0]
        assert record["wet_years"] == 1 and record["precipitation_sum"] == 1.7
        assert record["sunrise"] == "08:45"  # the most recent year's

    def test_no_samples(self):
        record = tw.typical_record(dt.date(2026, 11, 6), [])
        assert record["years"] == 0 and record["temp_max"] is None and record["wet_years"] is None


class TestGetTripWeather:
    def test_unknown_place(self, wired):
        assert tw.get_trip_weather("Nowhere", TODAY, TODAY, today=TODAY) is None

    def test_forecast_only_with_air(self, wired):
        start = TODAY + dt.timedelta(days=1)
        row = tw.get_trip_weather("Paris", start, start + dt.timedelta(days=2), today=TODAY)
        assert [d["source"] for d in row["days"]] == ["forecast"] * 3
        assert wired["history"] == [] and row["typical_years"] is None
        assert wired["air"] == [(start, start + dt.timedelta(days=2))]
        first, second = row["days"][0]["air"], row["days"][1]["air"]
        assert first["us_aqi"] == 40 and first["hours"] == 24 and second["hours"] == 6
        assert row["days"][2]["air"] is None
        assert any("Air quality" in note for note in row["notes"])
        assert row["location"] == "Paris" and row["unit"] == "°C"

    def test_mixed_trip_and_empty_last_forecast_day(self, wired):
        start = TODAY + dt.timedelta(days=13)  # 3 forecast days, the third empty, then typical
        end = TODAY + dt.timedelta(days=17)
        row = tw.get_trip_weather("Paris", start, end, years=3, today=TODAY)
        sources = [d["source"] for d in row["days"]]
        assert sources == ["forecast", "forecast", "typical", "typical", "typical"]
        assert [d["date"] for d in row["days"]] == [d.isoformat() for d in tw.date_range(start, end)]
        assert row["typical_years"] == [2023, 2025]
        assert len(wired["history"]) == 3
        assert wired["history"][0] == (dt.date(2025, 11, 5), dt.date(2025, 11, 7))
        typical = row["days"][2]
        assert typical["years"] == 3 and typical["temp_max"] == 14.0  # mean of 15, 14, 13
        assert typical["temp_max_range"] == [13.0, 15.0] and typical["wet_years"] == 3
        assert wired["air"] == []  # the trip starts after the air-quality forecast
        assert any("2026-11-05 onwards is beyond the forecast" in n for n in row["notes"])

    def test_summary(self, wired):
        start = TODAY + dt.timedelta(days=14)
        row = tw.get_trip_weather("Paris", start, start + dt.timedelta(days=2), years=2, today=TODAY)
        summary = row["summary"]
        assert summary["forecast_days"] == 1 and summary["typical_days"] == 2
        assert summary["forecast_wet_days"] == 1 and summary["air_quality_days"] == 0
        assert summary["highest"] == {"date": row["days"][0]["date"], "temp_max": 15.0,
                                      "source": "forecast"}


class TestFormat:
    def test_pollen(self):
        assert tw.format_pollen({f: None for f in air_quality.POLLEN_FIELDS}) == "-"
        assert tw.format_pollen({f: 0.0 for f in air_quality.POLLEN_FIELDS}) == "none"
        air = {f: 0.0 for f in air_quality.POLLEN_FIELDS}
        air["birch_pollen"], air["grass_pollen"] = 3.2, 1.0
        assert tw.format_pollen(air) == "birch 3.2, grass 1"

    def test_report_sections(self, wired):
        start = TODAY + dt.timedelta(days=1)
        out = tw.format_trip(tw.get_trip_weather("Paris", start, TODAY + dt.timedelta(days=17),
                                                 years=2, today=TODAY))
        assert out.startswith("Trip weather for Paris, Île-de-France, France, 2026-10-22 to 2026-11-07")
        assert "\nForecast\n" in out
        assert "Typical weather, from the same dates in 2024-2025 (not a forecast)" in out
        assert "Air quality (the day's worst hour)" in out and "[6 h of forecast]" in out
        assert "Note: 2026-11-05 onwards is beyond the forecast" in out


class TestParseArgs:
    def test_end_defaults_to_start(self):
        args = tw.parse_args(["Paris", "--start", "2026-10-25"], today=TODAY)
        assert args.end == args.start == dt.date(2026, 10, 25)
        assert args.years == tw.DEFAULT_YEARS and args.unit == "celsius"

    def test_yesterday_allowed(self):
        tw.parse_args(["Paris", "--start", "2026-10-20"], today=TODAY)

    @pytest.mark.parametrize("argv", [
        ["--start", "25/10/2026"],
        ["--start", "2026-10-25", "--end", "2026-10-24"],
        ["--start", "2026-10-25", "--end", "2026-11-25"],
        ["--start", "2026-10-19"],
        ["--start", "2027-10-20", "--end", "2027-10-23"],
        ["--start", "2026-10-25", "--years", "0"],
        ["--start", "2026-10-25", "--years", "21"],
        [],
    ])
    def test_rejected_with_exit_2(self, argv):
        with pytest.raises(SystemExit) as exc:
            tw.parse_args(["Paris", *argv], today=TODAY)
        assert exc.value.code == 2


class TestMain:
    @pytest.fixture(autouse=True)
    def fixed_today(self, monkeypatch):
        monkeypatch.setattr(tw, "today_utc", lambda: TODAY)

    def test_json(self, wired, capsys):
        tw.main(["Paris", "--start", "2026-10-22", "--end", "2026-10-23", "--json"])
        row = json.loads(capsys.readouterr().out)
        assert row["attribution"] == tw.ATTRIBUTION and len(row["days"]) == 2
        assert row["admin1"] == "Île-de-France"

    def test_text_ends_with_attribution(self, wired, capsys):
        tw.main(["Paris", "--start", "2026-10-22"])
        out = capsys.readouterr().out
        assert out.startswith("Looking up trip weather for 'Paris'")
        assert out.rstrip().endswith(tw.ATTRIBUTION)

    def test_unknown_place_exits_1(self, wired, capsys):
        with pytest.raises(SystemExit) as exc:
            tw.main(["Nowhere", "--start", "2026-10-22", "--json"])
        assert exc.value.code == 1
        assert "No location found" in json.loads(capsys.readouterr().err)["error"]

    def test_request_error_exits_1(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise requests.HTTPError("400: Parameter 'start_date' is out of allowed range")

        monkeypatch.setattr(tw, "get_trip_weather", boom)
        with pytest.raises(SystemExit) as exc:
            tw.main(["Paris", "--start", "2026-10-22"])
        assert exc.value.code == 1 and "start_date" in capsys.readouterr().err
