"""Tests for earthquakes: the window, distance and time helpers, the USGS fetch and its errors, record assembly, report formatting, argument parsing and main()."""

import datetime as dt
import json

import pytest
import requests

import earthquakes as eq
from helpers import FakeResponse

TOKYO = {"name": "Tokyo", "admin1": "Tokyo", "country": "Japan", "country_code": "JP",
         "latitude": 35.69, "longitude": 139.69}
SF = {"name": "San Francisco", "admin1": "California", "country": "United States",
      "country_code": "US", "latitude": 37.77, "longitude": -122.42}


def _feature(mag=4.6, place="54 km E of Tomioka, Japan", time=1793060708167,
             coords=(141.625, 37.3869, 48.93), **props):
    return {
        "id": "us7000abcd",
        "properties": {"mag": mag, "magType": "mb", "place": place, "time": time,
                       "status": "reviewed", "tsunami": 0, "alert": None, "felt": None,
                       "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000abcd",
                       **props},
        "geometry": {"type": "Point", "coordinates": list(coords)},
    }


def _record(**overrides):
    row = {
        "location": "Tokyo", "admin1": "Tokyo", "country": "Japan",
        "latitude": 35.69, "longitude": 139.69,
        "radius_km": 300, "min_magnitude": 2.5, "start": "2026-09-27", "end": "2026-10-27",
        "order": "time", "limit": 20, "count": 0, "more": False, "earthquakes": [],
    }
    row.update(overrides)
    return row


class TestResolveWindow:
    TODAY = dt.date(2026, 10, 27)

    def test_default_is_last_30_days(self):
        assert eq.resolve_window(today=self.TODAY) == (dt.date(2026, 9, 28), self.TODAY)

    def test_days_counts_today(self):
        assert eq.resolve_window(days=7, today=self.TODAY) == (dt.date(2026, 10, 21), self.TODAY)
        assert eq.resolve_window(days=1, today=self.TODAY) == (self.TODAY, self.TODAY)

    def test_start_defaults_end_to_today(self):
        assert eq.resolve_window(start="2026-10-01", today=self.TODAY) == (
            dt.date(2026, 10, 1), self.TODAY)

    def test_start_and_end(self):
        assert eq.resolve_window(start="2020-01-01", end="2020-01-31", today=self.TODAY) == (
            dt.date(2020, 1, 1), dt.date(2020, 1, 31))

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError, match="before start"):
            eq.resolve_window(start="2026-10-10", end="2026-10-01", today=self.TODAY)

    def test_bad_date_raises(self):
        with pytest.raises(ValueError, match="invalid date"):
            eq.resolve_window(start="2026-13-01", today=self.TODAY)


class TestDistanceKm:
    def test_same_point_is_zero(self):
        assert eq.distance_km(35.0, 139.0, 35.0, 139.0) == 0

    def test_one_degree_of_latitude(self):
        assert eq.distance_km(0, 0, 1, 0) == pytest.approx(111.2, abs=0.1)

    def test_across_the_date_line(self):
        assert eq.distance_km(0, 179.5, 0, -179.5) == pytest.approx(111.2, abs=0.1)


class TestUtcTime:
    def test_epoch_millis(self):
        assert eq.utc_time(0) == "1970-01-01T00:00:00Z"
        assert eq.utc_time(1793060708167) == "2026-10-27T00:25:08Z"

    def test_none(self):
        assert eq.utc_time(None) is None


class TestFetchGeojson:
    def test_sends_format_and_params(self, monkeypatch):
        calls = []

        def fake_get(url, params, timeout):
            calls.append((url, params))
            return FakeResponse(json_data={"features": []})

        monkeypatch.setattr(eq.requests, "get", fake_get)
        assert eq.fetch_geojson({"latitude": 1}) == {"features": []}
        assert calls == [(eq.QUERY_URL, {"format": "geojson", "latitude": 1})]

    def test_no_content_is_no_events(self, monkeypatch):
        monkeypatch.setattr(eq.requests, "get",
                            lambda *a, **k: FakeResponse(status_code=204))
        assert eq.fetch_geojson({}) == {"features": []}

    def test_plain_text_error_reason_is_raised(self, monkeypatch):
        text = ('Error 400: Bad Request\n\nBad latitude value "99". '
                'Valid values are -90 <= latitude <= 90\n\nUsage details are available from ...')
        monkeypatch.setattr(eq.requests, "get", lambda *a, **k: FakeResponse(
            status_code=400, text=text, raise_for_status=requests.HTTPError("400 Client Error")))
        with pytest.raises(requests.HTTPError, match='400: Bad latitude value "99"'):
            eq.fetch_geojson({})

    def test_other_error_falls_back_to_raise_for_status(self, monkeypatch):
        monkeypatch.setattr(eq.requests, "get", lambda *a, **k: FakeResponse(
            status_code=503, text="", raise_for_status=requests.HTTPError("503 Server Error")))
        with pytest.raises(requests.HTTPError, match="503 Server Error"):
            eq.fetch_geojson({})


class TestQuakeRow:
    def test_flattens_feature(self):
        row = eq.quake_row(_feature(), 35.69, 139.69)
        assert row["time"] == "2026-10-27T00:25:08Z"
        assert row["magnitude"] == 4.6
        assert row["magnitude_type"] == "mb"
        assert row["place"] == "54 km E of Tomioka, Japan"
        assert (row["latitude"], row["longitude"], row["depth_km"]) == (37.3869, 141.625, 48.9)
        assert row["distance_km"] == round(eq.distance_km(35.69, 139.69, 37.3869, 141.625))
        assert row["status"] == "reviewed"
        assert row["tsunami"] is False
        assert row["url"].endswith("/us7000abcd")

    def test_tsunami_flag_is_bool(self):
        assert eq.quake_row(_feature(tsunami=1), 0, 0)["tsunami"] is True

    def test_missing_geometry_and_url(self):
        feature = _feature(url=None)
        feature["geometry"] = None
        row = eq.quake_row(feature, 0, 0)
        assert row["latitude"] is None and row["depth_km"] is None and row["distance_km"] is None
        assert row["url"] == eq.EVENT_PAGE_URL + "us7000abcd"


class TestGetEarthquakes:
    def _patch(self, monkeypatch, place, features):
        calls = []
        monkeypatch.setattr(eq, "geocode", lambda loc: place)
        monkeypatch.setattr(eq, "fetch_geojson",
                            lambda params: calls.append(params) or {"features": features})
        return calls

    def test_location_not_found(self, monkeypatch):
        calls = self._patch(monkeypatch, None, [])
        assert eq.get_earthquakes("zzz") is None
        assert calls == []

    def test_query_params(self, monkeypatch):
        calls = self._patch(monkeypatch, TOKYO, [])
        eq.get_earthquakes("Tokyo", radius_km=100, min_magnitude=4, first=dt.date(2026, 10, 1),
                           final=dt.date(2026, 10, 27), order="magnitude", limit=5)
        assert calls == [{
            "latitude": 35.69, "longitude": 139.69, "maxradiuskm": 100, "minmagnitude": 4,
            "starttime": "2026-10-01", "endtime": "2026-10-28",
            "orderby": "magnitude", "limit": 6,
        }]

    def test_defaults(self, monkeypatch):
        calls = self._patch(monkeypatch, SF, [])
        row = eq.get_earthquakes("San Francisco")
        params = calls[0]
        assert (params["maxradiuskm"], params["minmagnitude"]) == (300, 2.5)
        assert (params["orderby"], params["limit"]) == ("time", 21)
        first = dt.date.fromisoformat(params["starttime"])
        assert dt.date.fromisoformat(row["end"]) - first == dt.timedelta(days=29)

    def test_record(self, monkeypatch):
        self._patch(monkeypatch, TOKYO, [_feature(), _feature(mag=5.1)])
        row = eq.get_earthquakes("Tokyo", first=dt.date(2026, 10, 1), final=dt.date(2026, 10, 27))
        assert row["location"] == "Tokyo" and row["country"] == "Japan"
        assert (row["start"], row["end"]) == ("2026-10-01", "2026-10-27")
        assert row["count"] == 2 and row["more"] is False
        assert [q["magnitude"] for q in row["earthquakes"]] == [4.6, 5.1]

    def test_extra_feature_means_more(self, monkeypatch):
        self._patch(monkeypatch, TOKYO, [_feature()] * 3)
        row = eq.get_earthquakes("Tokyo", limit=2)
        assert row["count"] == 2 and row["more"] is True

    def test_coverage_note_outside_us_only(self, monkeypatch):
        self._patch(monkeypatch, TOKYO, [])
        assert eq.get_earthquakes("Tokyo")["coverage_note"] == eq.COVERAGE_NOTE
        self._patch(monkeypatch, SF, [])
        assert "coverage_note" not in eq.get_earthquakes("San Francisco")


class TestFormatEarthquakes:
    def test_none_found(self):
        out = eq.format_earthquakes(_record())
        assert out.splitlines()[0] == "Earthquakes within 300 km of Tokyo, Japan"
        assert "Magnitude 2.5+, 2026-09-27 to 2026-10-27 (UTC), newest first" in out
        assert "No earthquakes found." in out

    def test_rows_and_flags(self):
        quake = eq.quake_row(_feature(tsunami=1, alert="yellow", status="automatic"), 35.69, 139.69)
        out = eq.format_earthquakes(_record(order="magnitude", count=1, earthquakes=[quake]))
        assert "largest first" in out
        line = next(l for l in out.splitlines() if l.startswith("2026-10-27T00"))
        assert "4.6" in line and "48.9 km" in line and "Tomioka" in line
        assert "[tsunami flag, PAGER yellow, not yet reviewed]" in line

    def test_more_and_coverage_note(self):
        quake = eq.quake_row(_feature(), 35.69, 139.69)
        out = eq.format_earthquakes(_record(count=1, limit=1, more=True, earthquakes=[quake],
                                            coverage_note=eq.COVERAGE_NOTE))
        assert "showing the first 1 (raise --limit to see more)" in out
        assert f"Note: {eq.COVERAGE_NOTE}" in out


class TestParseArgs:
    def test_defaults(self):
        args = eq.parse_args(["Tokyo"])
        assert args.location == "Tokyo"
        assert (args.radius, args.min_magnitude, args.days) == (300, 2.5, None)
        assert (args.start, args.end, args.order, args.limit, args.json) == (
            None, None, "time", 20, False)

    def test_overrides(self):
        args = eq.parse_args(["Tokyo", "--radius", "50", "--min-magnitude", "4.5", "--days", "7",
                              "--order", "magnitude", "--limit", "5", "--json"])
        assert (args.radius, args.min_magnitude, args.days) == (50, 4.5, 7)
        assert (args.order, args.limit, args.json) == ("magnitude", 5, True)

    @pytest.mark.parametrize("argv", [
        ["Tokyo", "--radius", "0"],
        ["Tokyo", "--radius", "20001"],
        ["Tokyo", "--min-magnitude", "11"],
        ["Tokyo", "--min-magnitude", "big"],
        ["Tokyo", "--days", "0"],
        ["Tokyo", "--limit", "20001"],
        ["Tokyo", "--order", "depth"],
        ["Tokyo", "--days", "7", "--start", "2026-10-01"],
        ["Tokyo", "--end", "2026-10-01"],
    ])
    def test_rejected_with_exit_2(self, argv, capsys):
        with pytest.raises(SystemExit) as exc:
            eq.parse_args(argv)
        assert exc.value.code == 2


class TestMain:
    def test_json_output(self, monkeypatch, capsys):
        calls = []
        monkeypatch.setattr(eq, "get_earthquakes",
                            lambda loc, **kw: calls.append((loc, kw)) or _record())
        eq.main(["Tokyo", "--radius", "100", "--start", "2026-10-01", "--end", "2026-10-02",
                 "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["attribution"] == eq.ATTRIBUTION
        assert calls == [("Tokyo", {"radius_km": 100, "min_magnitude": 2.5,
                                    "first": dt.date(2026, 10, 1), "final": dt.date(2026, 10, 2),
                                    "order": "time", "limit": 20})]

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(eq, "get_earthquakes", lambda loc, **kw: _record())
        eq.main(["Tokyo"])
        out = capsys.readouterr().out
        assert out.startswith("Looking up earthquakes near 'Tokyo'...")
        assert "No earthquakes found." in out
        assert out.rstrip().endswith(eq.ATTRIBUTION)

    def test_attribution_credits_both_sources(self):
        assert "U.S. Geological Survey" in eq.ATTRIBUTION
        assert "Open-Meteo" in eq.ATTRIBUTION

    def test_not_found_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(eq, "get_earthquakes", lambda loc, **kw: None)
        with pytest.raises(SystemExit) as exc:
            eq.main(["Zzz", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "No location found matching 'Zzz'."}

    def test_request_error_exits_1(self, monkeypatch, capsys):
        def boom(loc, **kw):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(eq, "get_earthquakes", boom)
        with pytest.raises(SystemExit) as exc:
            eq.main(["Tokyo", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {"error": "down"}

    def test_bad_window_exits_1_before_fetching(self, monkeypatch, capsys):
        monkeypatch.setattr(eq, "get_earthquakes",
                            lambda loc, **kw: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            eq.main(["Tokyo", "--start", "2026-10-10", "--end", "2026-10-01"])
        assert exc.value.code == 1
        assert "Error: end date 2026-10-01 is before start date 2026-10-10" in capsys.readouterr().err
