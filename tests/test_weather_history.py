"""Tests for weather_history: window resolution, day records, summary, formatting, and main()."""

import datetime as dt
import json

import pytest
import requests

import weather_history as wh

TODAY = dt.date(2026, 10, 15)
PLACE = {"name": "X", "admin1": None, "country": "C", "latitude": 1, "longitude": 2}


def _daily():
    """An Open-Meteo archive ``daily`` block for two days."""
    return {
        "time": ["2024-01-01", "2024-01-02"],
        "weathercode": [0, 71],
        "temperature_2m_max": [5.0, 1.5],
        "temperature_2m_min": [1.0, -3.2],
        "temperature_2m_mean": [3.1, -0.8],
        "precipitation_sum": [0.4, 6.0],
        "rain_sum": [0.4, 0.0],
        "snowfall_sum": [0.0, 4.2],
        "windspeed_10m_max": [12.0, 30.5],
        "sunrise": ["2024-01-01T08:06", "2024-01-02T08:06"],
        "sunset": ["2024-01-01T16:02", "2024-01-02T16:03"],
        "daylight_duration": [28560.0, 28620.0],
    }


def _day(date, temp_max, temp_min, precip, snow=0.0):
    return {"date": date, "temp_max": temp_max, "temp_min": temp_min,
            "precipitation_sum": precip, "snowfall_sum": snow}


class TestResolveWindow:
    def _parse(self, *argv):
        return wh.parse_args(["X", *argv], today=TODAY)

    def test_single_date(self):
        args = self._parse("--date", "2024-01-01")
        assert args.start == args.end == dt.date(2024, 1, 1)

    def test_start_end(self):
        args = self._parse("--start", "2024-01-01", "--end", "2024-01-31")
        assert (args.start, args.end) == (dt.date(2024, 1, 1), dt.date(2024, 1, 31))

    def test_end_defaults_to_today(self):
        assert self._parse("--start", "2026-10-01").end == TODAY

    def test_earliest_date_and_today_allowed(self):
        assert self._parse("--date", "1940-01-01").start == wh.EARLIEST_DATE
        assert self._parse("--date", "2026-10-15").end == TODAY

    def test_full_range_allowed(self):
        args = self._parse("--start", "2024-01-01", "--end", "2024-12-31")  # 366 days
        assert (args.end - args.start).days + 1 == wh.MAX_RANGE_DAYS

    @pytest.mark.parametrize("argv,message", [
        ([], "give a --date"),
        (["--end", "2024-01-01"], "--end requires --start"),
        (["--date", "2024-01-01", "--start", "2024-01-01"], "cannot be combined"),
        (["--start", "2024-02-01", "--end", "2024-01-01"], "must not be before"),
        (["--date", "1939-12-31"], "starts on 1940-01-01"),
        (["--date", "2026-10-16"], "in the future"),
        (["--start", "2024-01-01", "--end", "2025-01-01"], "limited to 366 days"),
        (["--date", "2024-13-01"], "invalid date"),
    ])
    def test_rejected_with_exit_2(self, argv, message, capsys):
        with pytest.raises(SystemExit) as exc:
            self._parse(*argv)
        assert exc.value.code == 2
        assert message in capsys.readouterr().err


class TestGetHistory:
    def test_location_not_found(self, monkeypatch):
        monkeypatch.setattr(wh, "geocode", lambda loc: None)
        assert wh.get_history("zzz", TODAY, TODAY) is None

    def test_builds_day_records(self, monkeypatch):
        seen = []
        monkeypatch.setattr(wh, "geocode", lambda loc: PLACE)
        monkeypatch.setattr(wh, "fetch_daily_history",
                            lambda *a, **k: seen.append((a, k)) or _daily())
        start, end = dt.date(2024, 1, 1), dt.date(2024, 1, 2)
        row = wh.get_history("X", start, end, unit="fahrenheit")
        assert seen == [((1, 2, start, end), {"unit": "fahrenheit"})]
        assert (row["start_date"], row["end_date"], row["unit"]) == ("2024-01-01", "2024-01-02", "°F")
        assert row["days"][1] == {
            "date": "2024-01-02", "weather_code": 71, "condition": "Slight snow fall",
            "temp_max": 1.5, "temp_min": -3.2, "temp_mean": -0.8,
            "precipitation_sum": 6.0, "rain_sum": 0.0, "snowfall_sum": 4.2,
            "windspeed_max": 30.5, "sunrise": "08:06", "sunset": "16:03",
            "daylight_hours": 7.95, "polar": None,
        }
        assert row["summary"]["days"] == 2

    def test_missing_values_are_none(self, monkeypatch):
        monkeypatch.setattr(wh, "geocode", lambda loc: PLACE)
        monkeypatch.setattr(wh, "fetch_daily_history", lambda *a, **k: {"time": ["2026-10-15"]})
        day = wh.get_history("X", TODAY, TODAY)["days"][0]
        assert day["condition"] is None and day["temp_max"] is None and day["sunrise"] is None


class TestFetchDailyHistory:
    def test_params(self, monkeypatch):
        seen = []
        monkeypatch.setattr(wh, "fetch_json", lambda url, params: seen.append((url, params)) or {})
        assert wh.fetch_daily_history(1, 2, dt.date(2024, 1, 1), dt.date(2024, 1, 5)) == {}
        url, params = seen[0]
        assert url == wh.ARCHIVE_URL
        assert (params["start_date"], params["end_date"]) == ("2024-01-01", "2024-01-05")
        assert params["timezone"] == "auto" and params["daily"] == wh.DAILY_FIELDS


class TestSummarize:
    def test_aggregates(self):
        days = [_day("d1", 10.0, 2.0, 0.4), _day("d2", 14.0, 6.0, 5.0, snow=1.5),
                _day("d3", 12.0, -1.0, 1.0)]
        assert wh.summarize(days) == {
            "days": 3, "days_with_data": 3, "avg_temp_max": 12.0, "avg_temp_min": 2.3,
            "warmest": {"date": "d2", "temp_max": 14.0},
            "coldest": {"date": "d3", "temp_min": -1.0},
            "total_precipitation": 6.4, "wet_days": 2, "total_snowfall": 1.5,
        }

    def test_single_day_has_no_summary(self):
        assert wh.summarize([_day("d1", 10.0, 2.0, 0.0)]) is None

    def test_missing_values_left_out(self):
        days = [_day("d1", 10.0, 2.0, 1.2), _day("d2", None, None, None, snow=None)]
        summary = wh.summarize(days)
        assert (summary["days"], summary["days_with_data"]) == (2, 1)
        assert summary["avg_temp_max"] == 10.0 and summary["total_precipitation"] == 1.2

    def test_no_data_at_all(self):
        assert wh.summarize([_day("d1", None, None, None), _day("d2", None, None, None)]) is None


class TestFormatHistory:
    def _row(self, monkeypatch):
        monkeypatch.setattr(wh, "geocode", lambda loc: PLACE)
        monkeypatch.setattr(wh, "fetch_daily_history", lambda *a, **k: _daily())
        return wh.get_history("X", dt.date(2024, 1, 1), dt.date(2024, 1, 2))

    def test_range_table_and_summary(self, monkeypatch):
        out = wh.format_history(self._row(monkeypatch))
        lines = out.splitlines()
        assert lines[0] == "Weather for X, C, 2024-01-01 to 2024-01-02"
        assert "Snow cm" in lines[2] and "Daylight" in lines[2]
        assert lines[5].split()[:4] == ["2024-01-02", "Slight", "snow", "fall"]
        assert lines[5].split()[-3:] == ["08:06", "16:03", "7h57m"]
        assert "Summary (2 days)" in out
        assert "Coldest night        -3.2°C on 2024-01-02" in out
        assert "Total precipitation  6.4 mm (1 wet days, >= 1 mm)" in out
        assert "Total snowfall       4.2 cm" in out

    def test_single_day_title_and_no_summary(self, monkeypatch):
        row = self._row(monkeypatch)
        row.update(end_date="2024-01-01", days=row["days"][:1], summary=None)
        out = wh.format_history(row)
        assert out.splitlines()[0] == "Weather for X, C on 2024-01-01"
        assert "Summary" not in out

    def test_missing_values_and_polar_night(self, monkeypatch):
        row = self._row(monkeypatch)
        row["days"][0].update(condition=None, temp_mean=None, sunrise=None, sunset=None,
                              daylight_hours=0.0, polar="night")
        row["summary"]["days_with_data"] = 1
        out = wh.format_history(row)
        assert "polar night" in out.splitlines()[4]
        assert "(1 day(s) have no data yet)" in out


class TestMain:
    def test_request_error_exits_json(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise requests.RequestException("400: out of allowed range")

        monkeypatch.setattr(wh, "get_history", boom)
        with pytest.raises(SystemExit) as exc:
            wh.main(["X", "--date", "2024-01-01", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "400: out of allowed range"}

    def test_not_found_exits(self, monkeypatch, capsys):
        monkeypatch.setattr(wh, "get_history", lambda *a, **k: None)
        with pytest.raises(SystemExit) as exc:
            wh.main(["zzz", "--date", "2024-01-01"])
        assert exc.value.code == 1
        assert "No location found" in capsys.readouterr().err

    def test_json_output(self, monkeypatch, capsys):
        seen = []
        record = {"location": "X", "days": []}
        monkeypatch.setattr(wh, "get_history", lambda *a, **k: seen.append((a, k)) or record)
        wh.main(["X", "--start", "2024-01-01", "--end", "2024-01-03", "--unit", "fahrenheit", "--json"])
        assert json.loads(capsys.readouterr().out) == record
        assert seen == [(("X", dt.date(2024, 1, 1), dt.date(2024, 1, 3)), {"unit": "fahrenheit"})]

    def test_text_output_has_progress_line(self, monkeypatch, capsys):
        monkeypatch.setattr(wh, "geocode", lambda loc: PLACE)
        monkeypatch.setattr(wh, "fetch_daily_history", lambda *a, **k: _daily())
        wh.main(["X", "--start", "2024-01-01", "--end", "2024-01-02"])
        out = capsys.readouterr().out
        assert out.startswith("Looking up the weather for 'X' on 2024-01-01 to 2024-01-02...")
        assert "Summary (2 days)" in out

    def test_bad_window_exits_2_before_fetch(self, monkeypatch):
        monkeypatch.setattr(wh, "get_history", lambda *a, **k: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            wh.main(["X"])
        assert exc.value.code == 2
