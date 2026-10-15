"""Tests for weather_forecast: _valid_days, uv_category, forecast assembly, formatting, and main()."""

import argparse
import json

import pytest
import requests

import weather_forecast as wf


def _day(**overrides):
    """A get_forecast() day record, with the UV and sun fields filled in."""
    day = {"date": "2024-01-01", "condition": "Clear sky", "temp_max": 5, "temp_min": 1,
           "precipitation_sum": 0, "precipitation_probability_max": 10, "windspeed_max": 12,
           "uv_index_max": 6.4, "uv_category": "High", "sunrise": "07:58",
           "sunset": "16:02", "daylight_hours": 8.07, "polar": None}
    day.update(overrides)
    return day


class TestValidDays:
    @pytest.mark.parametrize("raw,expected", [("1", 1), ("5", 5), ("16", 16)])
    def test_valid(self, raw, expected):
        assert wf._valid_days(raw) == expected

    @pytest.mark.parametrize("raw", ["0", "17", "-1", "100"])
    def test_out_of_range(self, raw):
        with pytest.raises(argparse.ArgumentTypeError, match="between 1 and 16"):
            wf._valid_days(raw)

    def test_non_integer(self):
        with pytest.raises(argparse.ArgumentTypeError, match="must be an integer"):
            wf._valid_days("abc")


class TestUvCategory:
    @pytest.mark.parametrize("uv,expected", [
        (0, "Low"), (2.4, "Low"), (2.5, "Moderate"), (5.4, "Moderate"), (6, "High"),
        (7.4, "High"), (8, "Very high"), (10.4, "Very high"), (10.6, "Extreme"), (13, "Extreme"),
    ])
    def test_who_bands(self, uv, expected):
        assert wf.uv_category(uv) == expected

    def test_missing(self):
        assert wf.uv_category(None) is None


class TestGetForecast:
    def test_location_not_found(self, monkeypatch):
        monkeypatch.setattr(wf, "geocode", lambda loc: None)
        assert wf.get_forecast("zzz") is None

    def test_empty_time_gives_no_days(self, monkeypatch):
        monkeypatch.setattr(wf, "geocode", lambda loc: {"name": "X", "latitude": 1, "longitude": 2})
        monkeypatch.setattr(wf, "fetch_daily_forecast", lambda *a, **k: {"time": []})
        assert wf.get_forecast("X")["days"] == []

    def test_builds_day_records(self, monkeypatch):
        monkeypatch.setattr(wf, "geocode", lambda loc: {
            "name": "X", "admin1": "X", "country": "C", "latitude": 1, "longitude": 2,
        })
        daily = {
            "time": ["2024-01-01", "2024-01-02"],
            "weathercode": [0, 61],
            "temperature_2m_max": [5, 6],
            "temperature_2m_min": [1, 2],
            "precipitation_sum": [0, 3],
            "precipitation_probability_max": [10, 80],
            "windspeed_10m_max": [12, 20],
            "uv_index_max": [2.1, 8.3],
            "sunrise": ["2024-01-01T07:58", "2024-01-02T07:58"],
            "sunset": ["2024-01-01T16:02", "2024-01-02T16:03"],
            "daylight_duration": [29052.0, 29124.0],
        }
        monkeypatch.setattr(wf, "fetch_daily_forecast", lambda *a, **k: daily)
        row = wf.get_forecast("X", days=2, unit="fahrenheit")
        assert row["unit"] == "°F"
        assert len(row["days"]) == 2
        assert row["days"][0]["condition"] == "Clear sky"
        assert row["days"][1]["condition"] == "Slight rain"
        assert row["days"][1]["temp_max"] == 6
        assert (row["days"][1]["uv_index_max"], row["days"][1]["uv_category"]) == (8.3, "Very high")
        assert (row["days"][0]["sunrise"], row["days"][0]["sunset"]) == ("07:58", "16:02")
        assert row["days"][0]["daylight_hours"] == 8.07

    def test_missing_uv_and_sun_series_give_none(self, monkeypatch):
        monkeypatch.setattr(wf, "geocode", lambda loc: {"name": "X", "latitude": 1, "longitude": 2})
        daily = {"time": ["2024-01-01"], "weathercode": [0], "temperature_2m_max": [5],
                 "temperature_2m_min": [1], "precipitation_sum": [0],
                 "precipitation_probability_max": [10], "windspeed_10m_max": [12]}
        monkeypatch.setattr(wf, "fetch_daily_forecast", lambda *a, **k: daily)
        day = wf.get_forecast("X")["days"][0]
        assert day["uv_index_max"] is None and day["uv_category"] is None
        assert day["sunrise"] is None and day["daylight_hours"] is None

    def test_requests_uv_and_sun_fields(self):
        for field in ("uv_index_max", "sunrise", "sunset", "daylight_duration"):
            assert field in wf.DAILY_FIELDS.split(",")


class TestFormatForecast:
    def test_header_and_rows(self):
        row = {"location": "X", "admin1": None, "country": None, "unit": "°C", "days": [_day()]}
        out = wf.format_forecast(row)
        assert out.splitlines()[0] == "1-day forecast for X"
        assert "Clear sky" in out
        assert "2024-01-01" in out

    def test_shows_precipitation_amount_and_chance(self):
        row = {"location": "X", "admin1": None, "country": None, "unit": "°C",
               "days": [_day(condition="Slight rain", precipitation_sum=3.4,
                             precipitation_probability_max=72)]}
        lines = wf.format_forecast(row).splitlines()
        assert "Precip mm" in lines[2] and "Precip %" in lines[2]
        assert "3.4" in lines[4] and "72" in lines[4]

    def test_sun_and_uv_table(self):
        row = {"location": "X", "admin1": None, "country": None, "unit": "°C", "days": [_day()]}
        lines = wf.format_forecast(row).splitlines()
        assert "UV max" in lines[6] and "Sunrise" in lines[6] and "Daylight" in lines[6]
        assert lines[8].split() == ["2024-01-01", "6.4", "High", "07:58", "16:02", "8h04m"]

    def test_polar_and_missing_values(self):
        row = {"location": "X", "admin1": None, "country": None, "unit": "°C",
               "days": [_day(uv_index_max=None, uv_category=None, sunrise=None, sunset=None,
                             daylight_hours=0.0, polar="night")]}
        last = wf.format_forecast(row).splitlines()[-1]
        assert last.split() == ["2024-01-01", "-", "-", "polar", "night", "0h00m"]


class TestMain:
    def test_request_error_exits(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise requests.RequestException("down")

        monkeypatch.setattr(wf, "get_forecast", boom)
        with pytest.raises(SystemExit):
            wf.main(["X", "--json"])
        assert json.loads(capsys.readouterr().err) == {"error": "down"}

    def test_not_found_exits(self, monkeypatch, capsys):
        monkeypatch.setattr(wf, "get_forecast", lambda *a, **k: None)
        with pytest.raises(SystemExit):
            wf.main(["zzz"])
        assert "No location found" in capsys.readouterr().err

    def test_json_output(self, monkeypatch, capsys):
        record = {"location": "X", "days": []}
        monkeypatch.setattr(wf, "get_forecast", lambda *a, **k: record)
        wf.main(["X", "--json"])
        assert json.loads(capsys.readouterr().out) == record
