"""Tests for weather: weather-code lookup, place formatting and fields, fetch_json errors,
daily-series and sun helpers, geocode/get_weather, and main()."""

import json

import pytest
import requests

import weather
from helpers import FakeResponse


class TestWeatherDescription:
    def test_known_code(self):
        assert weather.weather_description(0) == "Clear sky"
        assert weather.weather_description(95) == "Thunderstorm"

    def test_unknown_code(self):
        assert weather.weather_description(123) == "Unknown (code 123)"

    def test_none_code(self):
        assert weather.weather_description(None) == "Unknown (code None)"


class TestFormatPlace:
    def test_location_only(self):
        assert weather.format_place({"location": "London"}) == "London"

    def test_location_admin1_country(self):
        row = {"location": "London", "admin1": "England", "country": "United Kingdom"}
        assert weather.format_place(row) == "London, England, United Kingdom"

    def test_admin1_equal_to_location_is_dropped(self):
        row = {"location": "Tokyo", "admin1": "Tokyo", "country": "Japan"}
        assert weather.format_place(row) == "Tokyo, Japan"

    def test_missing_admin1_and_country(self):
        assert weather.format_place({"location": "Nowhere", "admin1": None, "country": None}) == "Nowhere"


class TestPlaceFields:
    def test_maps_geocode_match(self):
        place = {"name": "Paris", "admin1": "Île-de-France", "country": "France",
                 "latitude": 48.85, "longitude": 2.35, "population": 2_000_000}
        assert weather.place_fields(place) == {
            "location": "Paris", "admin1": "Île-de-France", "country": "France",
            "latitude": 48.85, "longitude": 2.35,
        }

    def test_missing_fields_are_none(self):
        assert weather.place_fields({"name": "X"}) == {
            "location": "X", "admin1": None, "country": None, "latitude": None, "longitude": None,
        }


class TestFetchJson:
    def _patch(self, monkeypatch, response):
        monkeypatch.setattr(weather.requests, "get", lambda url, **kwargs: response)

    def test_returns_json(self, monkeypatch):
        self._patch(monkeypatch, FakeResponse(json_data={"ok": 1}))
        assert weather.fetch_json("u", {}) == {"ok": 1}

    def test_open_meteo_reason_is_surfaced(self, monkeypatch):
        body = {"error": True, "reason": "Parameter 'end_date' is out of allowed range"}
        self._patch(monkeypatch, FakeResponse(json_data=body, status_code=400))
        with pytest.raises(requests.HTTPError, match="400: Parameter 'end_date' is out of allowed range"):
            weather.fetch_json("u", {})

    def test_error_without_reason_uses_raise_for_status(self, monkeypatch):
        error = requests.HTTPError("503 Server Error")
        self._patch(monkeypatch, FakeResponse(json_data=None, status_code=503, raise_for_status=error))
        with pytest.raises(requests.HTTPError, match="503 Server Error"):
            weather.fetch_json("u", {})


class TestDailyValue:
    def test_present_missing_and_short(self):
        daily = {"a": [1, None]}
        assert weather.daily_value(daily, "a", 0) == 1
        assert weather.daily_value(daily, "a", 1) is None
        assert weather.daily_value(daily, "a", 5) is None
        assert weather.daily_value(daily, "b", 0) is None


class TestSunFields:
    def test_local_clock_times_and_hours(self):
        daily = {"sunrise": ["2024-06-01T05:43"], "sunset": ["2024-06-01T21:12"],
                 "daylight_duration": [55740.0]}
        assert weather.sun_fields(daily, 0) == {
            "sunrise": "05:43", "sunset": "21:12", "daylight_hours": 15.48, "polar": None}

    @pytest.mark.parametrize("seconds,polar", [(0.0, "night"), (86400.0, "day")])
    def test_polar_placeholders_dropped(self, seconds, polar):
        daily = {"sunrise": ["2025-12-21T00:00"], "sunset": ["2025-12-21T00:00"],
                 "daylight_duration": [seconds]}
        fields = weather.sun_fields(daily, 0)
        assert (fields["sunrise"], fields["sunset"], fields["polar"]) == (None, None, polar)
        assert fields["daylight_hours"] == seconds / 3600

    def test_missing_series(self):
        assert weather.sun_fields({}, 0) == {
            "sunrise": None, "sunset": None, "daylight_hours": None, "polar": None}


class TestFormatSunAndDaylight:
    @pytest.mark.parametrize("day,expected", [
        ({"sunrise": "06:47", "sunset": "18:52", "polar": None}, ("06:47", "18:52")),
        ({"sunrise": None, "sunset": None, "polar": "night"}, ("polar night", "")),
        ({"sunrise": None, "sunset": None, "polar": "day"}, ("midnight sun", "")),
        ({"sunrise": None, "sunset": None, "polar": None}, ("-", "-")),
    ])
    def test_format_sun(self, day, expected):
        assert weather.format_sun(day) == expected

    @pytest.mark.parametrize("hours,expected", [
        (12.09, "12h05m"), (0.0, "0h00m"), (24.0, "24h00m"), (9.999, "10h00m"), (None, "-"),
    ])
    def test_format_daylight(self, hours, expected):
        assert weather.format_daylight(hours) == expected


class TestGeocode:
    def test_returns_first_result(self, monkeypatch):
        monkeypatch.setattr(
            weather, "fetch_json",
            lambda url, params: {"results": [{"name": "Paris"}, {"name": "Paris TX"}]},
        )
        assert weather.geocode("Paris") == {"name": "Paris"}

    def test_no_results_returns_none(self, monkeypatch):
        monkeypatch.setattr(weather, "fetch_json", lambda url, params: {"results": []})
        assert weather.geocode("zzz") is None

    def test_missing_results_key_returns_none(self, monkeypatch):
        monkeypatch.setattr(weather, "fetch_json", lambda url, params: {})
        assert weather.geocode("zzz") is None


class TestGetWeather:
    def test_location_not_found_returns_none(self, monkeypatch):
        monkeypatch.setattr(weather, "geocode", lambda loc: None)
        assert weather.get_weather("zzz") is None

    def test_assembles_record(self, monkeypatch):
        monkeypatch.setattr(weather, "geocode", lambda loc: {
            "name": "Berlin", "admin1": "Berlin", "country": "Germany",
            "latitude": 52.5, "longitude": 13.4,
        })
        monkeypatch.setattr(weather, "fetch_current_weather", lambda lat, lon, unit="celsius": {
            "temperature": 9.0, "windspeed": 12.0, "winddirection": 200,
            "weathercode": 3, "time": "2024-01-01T12:00",
        })
        row = weather.get_weather("Berlin", unit="fahrenheit")
        assert row["location"] == "Berlin"
        assert row["condition"] == "Overcast"
        assert row["unit"] == "°F"
        assert row["temperature"] == 9.0


class TestParseArgs:
    def test_defaults(self):
        args = weather.parse_args(["London"])
        assert args.location == "London"
        assert args.unit == "celsius"
        assert args.json is False

    def test_flags(self):
        args = weather.parse_args(["London", "--unit", "fahrenheit", "--json"])
        assert args.unit == "fahrenheit"
        assert args.json is True

    def test_invalid_unit_rejected(self):
        with pytest.raises(SystemExit):
            weather.parse_args(["London", "--unit", "kelvin"])


class TestMain:
    def test_request_error_exits_json(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise requests.RequestException("network down")

        monkeypatch.setattr(weather, "get_weather", boom)
        with pytest.raises(SystemExit) as exc:
            weather.main(["London", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "network down"}

    def test_location_not_found_exits(self, monkeypatch, capsys):
        monkeypatch.setattr(weather, "get_weather", lambda *a, **k: None)
        with pytest.raises(SystemExit):
            weather.main(["zzz"])
        assert "No location found" in capsys.readouterr().err

    def test_json_output(self, monkeypatch, capsys):
        record = {"location": "X", "temperature": 1, "unit": "°C"}
        monkeypatch.setattr(weather, "get_weather", lambda *a, **k: record)
        weather.main(["X", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["temperature"] == 1
        # Open-Meteo's CC-BY 4.0 licence requires the credit on every result.
        assert payload["attribution"] == weather.ATTRIBUTION
        assert "Open-Meteo.com" in weather.ATTRIBUTION and "CC BY 4.0" in weather.ATTRIBUTION

    def test_text_output(self, monkeypatch, capsys):
        record = {
            "location": "X", "admin1": None, "country": None, "condition": "Clear sky",
            "temperature": 1, "unit": "°C", "windspeed": 2, "winddirection": 3,
            "time": "t",
        }
        monkeypatch.setattr(weather, "get_weather", lambda *a, **k: record)
        weather.main(["X"])
        out = capsys.readouterr().out
        assert "Weather for X" in out
        assert "Clear sky" in out
        assert out.rstrip().endswith(weather.ATTRIBUTION)
