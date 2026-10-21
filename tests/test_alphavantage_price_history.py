"""Tests for alphavantage_price_history: fetch_daily request/refusals, extract_rows,
history_note, main() output/exit paths."""

import datetime as dt
import json

import pytest
import requests

import alphavantage_price_history as av
import daily_prices
from helpers import FakeResponse

KEY = "secret-key"


def _bar(close="10.0000"):
    return {"1. open": "9.5000", "2. high": "10.5000", "3. low": "9.0000",
            "4. close": close, "5. volume": "100"}


def _payload(dates):
    return {"Meta Data": {"2. Symbol": "AAA", "5. Time Zone": "US/Eastern"},
            av.SERIES_KEY: {date: _bar() for date in dates}}


def _sessions(count, start=dt.date(2026, 1, 1)):
    return [(start + dt.timedelta(days=i)).isoformat() for i in range(count)]


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setattr(av, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", KEY)


class _FixedDate(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


class TestFetchDaily:
    def _capture(self, monkeypatch, response):
        calls = []

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return response

        monkeypatch.setattr(av.requests, "get", fake_get)
        return calls

    def test_compact_request(self, monkeypatch):
        calls = self._capture(monkeypatch, FakeResponse(json_data=_payload(["2026-10-20"])))
        av.fetch_daily("TSCO.LON", KEY)
        url, kwargs = calls[0]
        assert url == av.QUERY_URL
        assert kwargs["params"] == {"function": "TIME_SERIES_DAILY", "symbol": "TSCO.LON",
                                    "outputsize": "compact", "apikey": KEY}
        assert kwargs["timeout"] == av.REQUEST_TIMEOUT

    def test_full_request(self, monkeypatch):
        calls = self._capture(monkeypatch, FakeResponse(json_data=_payload(["2026-10-20"])))
        av.fetch_daily("AAPL", KEY, full=True)
        assert calls[0][1]["params"]["outputsize"] == "full"

    @pytest.mark.parametrize("key", av.MESSAGE_KEYS)
    def test_refusal_message_raised(self, monkeypatch, key):
        self._capture(monkeypatch, FakeResponse(json_data={key: "nope"}))
        with pytest.raises(ValueError, match="^nope$"):
            av.fetch_daily("X", KEY)

    def test_empty_body(self, monkeypatch):
        self._capture(monkeypatch, FakeResponse(json_data={}))
        with pytest.raises(ValueError, match="empty response"):
            av.fetch_daily("X", KEY)

    def test_missing_series(self, monkeypatch):
        self._capture(monkeypatch, FakeResponse(json_data={"Meta Data": {}}))
        with pytest.raises(ValueError, match="no 'Time Series"):
            av.fetch_daily("X", KEY)

    def test_http_error(self, monkeypatch):
        self._capture(monkeypatch, FakeResponse(status_code=503, reason="Service Unavailable"))
        with pytest.raises(ValueError, match="HTTP 503"):
            av.fetch_daily("X", KEY)


class TestExtractRows:
    def test_sorted_strings_converted_no_adj(self):
        rows = av.extract_rows(_payload(["2026-10-20", "2026-10-19"]))
        assert [r["date"] for r in rows] == ["2026-10-19", "2026-10-20"]
        assert rows[0] == {"date": "2026-10-19", "open": 9.5, "high": 10.5, "low": 9.0,
                           "close": 10.0, "adj_close": None, "volume": 100}

    def test_skips_bar_without_close(self):
        payload = _payload(["2026-10-20"])
        payload[av.SERIES_KEY]["2026-10-19"] = _bar(close="")
        assert [r["date"] for r in av.extract_rows(payload)] == ["2026-10-20"]


class TestHistoryNote:
    def _rows(self, count):
        return [{"date": d} for d in _sessions(count)]

    def test_note_when_window_starts_before_compact_data(self):
        note = av.history_note(self._rows(100), dt.date(2025, 6, 1), full=False)
        assert "latest 100 sessions" in note and "2026-01-01" in note

    def test_no_note_inside_compact_data(self):
        assert av.history_note(self._rows(100), dt.date(2026, 2, 1), full=False) is None

    def test_no_note_with_full(self):
        assert av.history_note(self._rows(100), dt.date(2025, 6, 1), full=True) is None

    def test_no_note_for_short_listing(self):
        # Fewer than 100 sessions means the whole history came back.
        assert av.history_note(self._rows(40), dt.date(2025, 6, 1), full=False) is None


class TestMain:
    def _wire(self, monkeypatch, payload):
        monkeypatch.setattr(av, "fetch_daily", lambda symbol, key, full=False: payload)
        monkeypatch.setattr(daily_prices.dt, "date", _FixedDate)

    def test_json_last_trims(self, monkeypatch, capsys, api_key):
        self._wire(monkeypatch, _payload([f"2026-10-{d:02d}" for d in range(14, 21)]))
        av.main(["TSCO.LON", "--last", "2", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload == {
            "symbol": "TSCO.LON", "source": "Alpha Vantage", "notes": [],
            "prices": payload["prices"],
        }
        assert [r["date"] for r in payload["prices"]] == ["2026-10-19", "2026-10-20"]

    def test_history_note_in_json(self, monkeypatch, capsys, api_key):
        self._wire(monkeypatch, _payload(_sessions(100, start=dt.date(2026, 6, 1))))
        av.main(["RELIANCE.BSE", "--start", "2026-01-01", "--json"])
        notes = json.loads(capsys.readouterr().out)["notes"]
        assert len(notes) == 1 and "--full" in notes[0]

    def test_text_table(self, monkeypatch, capsys, api_key):
        self._wire(monkeypatch, _payload(["2026-10-20"]))
        av.main(["TSCO.LON"])
        assert "TSCO.LON - Alpha Vantage - 1 session(s)" in capsys.readouterr().out

    def test_refusal_exits_1(self, monkeypatch, capsys, api_key):
        def refuse(symbol, key, full=False):
            raise ValueError("Invalid API call.")

        monkeypatch.setattr(av, "fetch_daily", refuse)
        with pytest.raises(SystemExit) as exc:
            av.main(["D05.SGX"])
        assert exc.value.code == 1
        assert "Invalid API call." in capsys.readouterr().err

    def test_network_error_redacts_key(self, monkeypatch, capsys, api_key):
        def boom(symbol, key, full=False):
            raise requests.ConnectionError(f"failed: {av.QUERY_URL}?apikey={key}")

        monkeypatch.setattr(av, "fetch_daily", boom)
        with pytest.raises(SystemExit):
            av.main(["AAPL", "--json"])
        error = json.loads(capsys.readouterr().err)["error"]
        assert KEY not in error and "<redacted>" in error

    def test_missing_key_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(av, "load_dotenv", lambda *a, **k: None)
        monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            av.main(["AAPL"])
        assert exc.value.code == 1
        assert "ALPHAVANTAGE_API_KEY" in capsys.readouterr().err

    def test_end_without_start_exits_1(self, capsys):
        with pytest.raises(SystemExit) as exc:
            av.main(["AAPL", "--end", "2026-10-01", "--json"])
        assert exc.value.code == 1
        assert "--end requires --start" in json.loads(capsys.readouterr().err)["error"]
