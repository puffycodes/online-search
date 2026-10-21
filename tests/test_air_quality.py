"""Tests for air_quality: us_aqi_category, air quality assembly, pollen and report formatting, and main()."""

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
            "birch_pollen": 12.5,
            "grass_pollen": 0.0,
            "time": "2026-01-01T00:00",
        }
        monkeypatch.setattr(aq, "fetch_current_air_quality", lambda *a, **k: current)
        row = aq.get_air_quality("X")
        assert row["location"] == "X"
        assert row["us_aqi"] == 42
        assert row["us_aqi_category"] == "Good"
        assert row["european_aqi"] == 20
        assert row["pm2_5"] == 8.1
        assert row["birch_pollen"] == 12.5
        assert row["grass_pollen"] == 0.0
        assert row["alder_pollen"] is None
        assert row["time"] == "2026-01-01T00:00"

    def test_requests_every_pollen_field(self):
        for field in aq.POLLEN_FIELDS:
            assert field in aq.CURRENT_FIELDS.split(",")

    def test_missing_us_aqi_gives_no_category(self, monkeypatch):
        monkeypatch.setattr(
            aq, "geocode", lambda loc: {"name": "X", "latitude": 1, "longitude": 2}
        )
        monkeypatch.setattr(aq, "fetch_current_air_quality", lambda *a, **k: {})
        row = aq.get_air_quality("X")
        assert row["us_aqi"] is None
        assert row["us_aqi_category"] is None


class TestFormatPollen:
    def test_all_none_is_not_available(self):
        row = {field: None for field in aq.POLLEN_FIELDS}
        assert aq.format_pollen(row) == "Pollen: not available (Europe only)"

    def test_missing_fields_count_as_none(self):
        assert aq.format_pollen({}) == "Pollen: not available (Europe only)"

    def test_lists_every_plant_in_order(self):
        row = {field: 0.0 for field in aq.POLLEN_FIELDS}
        row["birch_pollen"] = 12.5
        assert aq.format_pollen(row) == (
            "Pollen (grains/m³): alder 0.0, birch 12.5, grass 0.0, "
            "mugwort 0.0, olive 0.0, ragweed 0.0"
        )

    def test_zero_counts_are_available(self):
        row = {field: 0.0 for field in aq.POLLEN_FIELDS}
        assert "not available" not in aq.format_pollen(row)


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
        assert "Pollen: not available (Europe only)" in out
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
        payload = json.loads(capsys.readouterr().out)
        assert payload["us_aqi"] == 42
        assert payload["attribution"] == aq.ATTRIBUTION

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
        assert out.rstrip().endswith(aq.ATTRIBUTION)


class TestFetchHourlyAirQuality:
    def test_params(self, monkeypatch):
        import datetime as dt
        calls = []
        monkeypatch.setattr(aq, "fetch_json", lambda url, params: calls.append((url, params)) or {"hourly": {"time": []}})
        assert aq.fetch_hourly_air_quality(1, 2, dt.date(2026, 10, 22), dt.date(2026, 10, 24)) == {"time": []}
        url, params = calls[0]
        assert url == aq.AIR_QUALITY_URL and params["hourly"] == aq.HOURLY_FIELDS
        assert (params["start_date"], params["end_date"], params["timezone"]) == ("2026-10-22", "2026-10-24", "auto")


class TestDailyMaxima:
    def test_worst_hour_per_day_and_partial_days(self):
        hourly = {
            "time": ["2026-10-22T00:00", "2026-10-22T01:00", "2026-10-23T00:00", "2026-10-24T00:00"],
            "us_aqi": [40, 120, 30, None],
            "european_aqi": [20, 35, None, None],
            "birch_pollen": [0.5, 2.0, None, None],
        }
        days = aq.daily_maxima(hourly)
        assert set(days) == {"2026-10-22", "2026-10-23"}
        first = days["2026-10-22"]
        assert (first["us_aqi"], first["european_aqi"], first["birch_pollen"]) == (120, 35, 2.0)
        assert first["us_aqi_category"] == "Unhealthy for Sensitive Groups" and first["hours"] == 2
        assert first["grass_pollen"] is None
        assert days["2026-10-23"]["european_aqi"] is None and days["2026-10-23"]["hours"] == 1

    def test_empty(self):
        assert aq.daily_maxima({}) == {}
