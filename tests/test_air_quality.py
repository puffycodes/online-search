"""Tests for air_quality: us_aqi_category, air quality assembly, formatting, and main()."""

import json

import pytest
import requests

import air_quality as aq


class TestUsAqiCategory:
    def test_none_returns_none(self):
        assert aq.us_aqi_category(None) is None

    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, "Good"),
            (50, "Good"),
            (51, "Moderate"),
            (100, "Moderate"),
            (101, "Unhealthy for Sensitive Groups"),
            (150, "Unhealthy for Sensitive Groups"),
            (151, "Unhealthy"),
            (200, "Unhealthy"),
            (201, "Very Unhealthy"),
            (300, "Very Unhealthy"),
            (301, "Hazardous"),
            (500, "Hazardous"),
        ],
    )
    def test_bands(self, value, expected):
        assert aq.us_aqi_category(value) == expected


class TestGetAirQuality:
    def test_location_not_found(self, monkeypatch):
        monkeypatch.setattr(aq, "geocode", lambda loc: None)
        assert aq.get_air_quality("zzz") is None

    def test_builds_flat_record(self, monkeypatch):
        monkeypatch.setattr(
            aq,
            "geocode",
            lambda loc: {
                "name": "X",
                "admin1": "Y",
                "country": "C",
                "latitude": 1,
                "longitude": 2,
            },
        )
        current = {
            "us_aqi": 42,
            "european_aqi": 20,
            "pm2_5": 8.1,
            "pm10": 15.2,
            "carbon_monoxide": 200.0,
            "nitrogen_dioxide": 10.5,
            "sulphur_dioxide": 2.3,
            "ozone": 60.0,
            "time": "2026-01-01T00:00",
        }
        monkeypatch.setattr(aq, "fetch_current_air_quality", lambda *a, **k: current)
        row = aq.get_air_quality("X")
        assert row["location"] == "X"
        assert row["us_aqi"] == 42
        assert row["us_aqi_category"] == "Good"
        assert row["european_aqi"] == 20
        assert row["pm2_5"] == 8.1
        assert row["time"] == "2026-01-01T00:00"

    def test_missing_us_aqi_gives_no_category(self, monkeypatch):
        monkeypatch.setattr(
            aq, "geocode", lambda loc: {"name": "X", "latitude": 1, "longitude": 2}
        )
        monkeypatch.setattr(aq, "fetch_current_air_quality", lambda *a, **k: {})
        row = aq.get_air_quality("X")
        assert row["us_aqi"] is None
        assert row["us_aqi_category"] is None


class TestFormatAirQuality:
    def test_includes_place_and_readings(self):
        row = {
            "location": "X",
            "admin1": None,
            "country": None,
            "us_aqi": 42,
            "us_aqi_category": "Good",
            "european_aqi": 20,
            "pm2_5": 8.1,
            "pm10": 15.2,
            "carbon_monoxide": 200.0,
            "nitrogen_dioxide": 10.5,
            "sulphur_dioxide": 2.3,
            "ozone": 60.0,
            "time": "2026-01-01T00:00",
        }
        out = aq.format_air_quality(row)
        assert out.splitlines()[0] == "Air quality for X"
        assert "US AQI: 42 (Good)" in out
        assert "European AQI: 20" in out
        assert "2026-01-01T00:00" in out


class TestParseArgs:
    def test_defaults(self):
        args = aq.parse_args(["Tokyo"])
        assert args.location == "Tokyo"
        assert args.json is False

    def test_json_flag(self):
        args = aq.parse_args(["Tokyo", "--json"])
        assert args.json is True


class TestMain:
    def test_request_error_exits(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise requests.RequestException("down")

        monkeypatch.setattr(aq, "get_air_quality", boom)
        with pytest.raises(SystemExit):
            aq.main(["X", "--json"])
        assert json.loads(capsys.readouterr().err) == {"error": "down"}

    def test_not_found_exits(self, monkeypatch, capsys):
        monkeypatch.setattr(aq, "get_air_quality", lambda *a, **k: None)
        with pytest.raises(SystemExit):
            aq.main(["zzz"])
        assert "No location found" in capsys.readouterr().err

    def test_json_output(self, monkeypatch, capsys):
        record = {"location": "X", "us_aqi": 42}
        monkeypatch.setattr(aq, "get_air_quality", lambda *a, **k: record)
        aq.main(["X", "--json"])
        assert json.loads(capsys.readouterr().out) == record

    def test_text_output(self, monkeypatch, capsys):
        record = {
            "location": "X",
            "admin1": None,
            "country": None,
            "us_aqi": 42,
            "us_aqi_category": "Good",
            "european_aqi": 20,
            "pm2_5": 8.1,
            "pm10": 15.2,
            "carbon_monoxide": 200.0,
            "nitrogen_dioxide": 10.5,
            "sulphur_dioxide": 2.3,
            "ozone": 60.0,
            "time": "2026-01-01T00:00",
        }
        monkeypatch.setattr(aq, "get_air_quality", lambda *a, **k: record)
        aq.main(["X"])
        out = capsys.readouterr().out
        assert "Looking up air quality for 'X'" in out
        assert "Air quality for X" in out
