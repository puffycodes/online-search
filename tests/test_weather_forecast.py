"""Tests for weather_forecast: _valid_days, forecast assembly, formatting, and main()."""

import argparse
import json

import pytest
import requests

import weather_forecast as wf


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
        }
        monkeypatch.setattr(wf, "fetch_daily_forecast", lambda *a, **k: daily)
        row = wf.get_forecast("X", days=2, unit="fahrenheit")
        assert row["unit"] == "°F"
        assert len(row["days"]) == 2
        assert row["days"][0]["condition"] == "Clear sky"
        assert row["days"][1]["condition"] == "Slight rain"
        assert row["days"][1]["temp_max"] == 6


class TestFormatForecast:
    def test_header_and_rows(self):
        row = {
            "location": "X", "admin1": None, "country": None, "unit": "°C",
            "days": [
                {"date": "2024-01-01", "condition": "Clear sky", "temp_max": 5, "temp_min": 1,
                 "precipitation_sum": 0, "precipitation_probability_max": 10, "windspeed_max": 12},
            ],
        }
        out = wf.format_forecast(row)
        assert out.splitlines()[0] == "1-day forecast for X"
        assert "Clear sky" in out
        assert "2024-01-01" in out


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
