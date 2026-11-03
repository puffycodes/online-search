"""Tests for exchange_rates: build_params, fetch_rates request/errors, rate_rows, formatting, main() output/exit paths."""

import datetime as dt
import json

import pytest
import requests

import daily_prices
import exchange_rates as fx
from helpers import FakeResponse


def _record(date, quote, rate, base="USD"):
    return {"date": date, "base": base, "quote": quote, "rate": rate}


class TestBuildParams:
    def test_latest_all_currencies(self):
        assert fx.build_params("USD") == {"base": "USD"}

    def test_quotes_joined(self):
        assert fx.build_params("USD", ["EUR", "SGD"]) == {"base": "USD", "quotes": "EUR,SGD"}

    def test_one_date(self):
        params = fx.build_params("USD", ["EUR"], date=dt.date(2026, 10, 24))
        assert params == {"base": "USD", "quotes": "EUR", "date": "2026-10-24"}

    def test_range_with_group(self):
        params = fx.build_params("EUR", ["USD"], start=dt.date(2026, 1, 1),
                                 end=dt.date(2026, 6, 30), group="month")
        assert params == {"base": "EUR", "quotes": "USD", "from": "2026-01-01",
                          "to": "2026-06-30", "group": "month"}


class TestFetchRates:
    def test_request(self, monkeypatch):
        calls = []

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(json_data=[_record("2026-10-27", "EUR", 0.89237)])

        monkeypatch.setattr(fx.requests, "get", fake_get)
        payload = fx.fetch_rates({"base": "USD", "quotes": "EUR"})
        assert payload[0]["rate"] == 0.89237
        url, kwargs = calls[0]
        assert url == "https://api.frankfurter.dev/v2/rates"
        assert kwargs["params"] == {"base": "USD", "quotes": "EUR"}
        assert kwargs["timeout"] == fx.REQUEST_TIMEOUT

    def test_invalid_currency_keeps_frankfurters_message(self, monkeypatch):
        monkeypatch.setattr(fx.requests, "get", lambda url, **k: FakeResponse(
            status_code=422,
            json_data={"status": 422, "message": "invalid currency: ZZZ"},
            raise_for_status=requests.HTTPError("422 Client Error"),
        ))
        with pytest.raises(requests.HTTPError, match="HTTP 422: invalid currency: ZZZ"):
            fx.fetch_rates({"base": "USD", "quotes": "ZZZ"})

    def test_non_list_body(self, monkeypatch):
        monkeypatch.setattr(fx.requests, "get", lambda url, **k: FakeResponse(
            json_data={"odd": True}))
        with pytest.raises(ValueError, match="unexpected response"):
            fx.fetch_rates({"base": "USD"})


class TestRateRows:
    def test_sorted_and_converted(self):
        rows = fx.rate_rows([
            _record("2026-10-27", "SGD", 1.2775),
            _record("2026-10-23", "BTC", 1.2272e-05),
            _record("2026-10-27", "EUR", 0.89237),
        ], amount=250)
        assert [(r["date"], r["quote"]) for r in rows] == [
            ("2026-10-23", "BTC"), ("2026-10-27", "EUR"), ("2026-10-27", "SGD")]
        assert rows[2]["converted"] == 319.375  # not 319.37499999999994
        assert rows[0]["converted"] == 0.003068  # a tiny rate keeps its digits
        assert rows[1]["rate"] == 0.89237

    def test_skips_incomplete_records(self):
        rows = fx.rate_rows([
            _record("2026-10-27", "EUR", None),
            {"date": "2026-10-27", "rate": 1.0},
            "junk",
            _record("2026-10-27", "GBP", 0.75),
        ])
        assert [r["quote"] for r in rows] == ["GBP"]

    def test_empty(self):
        assert fx.rate_rows([]) == []


class TestFormatting:
    @pytest.mark.parametrize("value, expected", [
        (1, "1"), (250.0, "250"), (1000, "1,000"), (2.5, "2.5"), (0.125, "0.125"),
    ])
    def test_amount_text(self, value, expected):
        assert fx.amount_text(value) == expected

    @pytest.mark.parametrize("value, expected", [
        (157.27, "157.2700"), (39317.5, "39,317.5000"), (0.89237, "0.8924"),
        (0.003068, "0.003068"), (1.2272e-05, "0.00001227"), (0, "0.0000"),
    ])
    def test_number_text(self, value, expected):
        assert fx.number_text(value) == expected


class TestParseArgs:
    def test_defaults(self):
        args = fx.parse_args(["usd"])
        assert args.base == "usd" and args.quotes == [] and args.amount == 1.0
        assert args.date is None and args.start is None and args.group is None

    @pytest.mark.parametrize("argv", [
        ["USD", "--amount", "0"],
        ["USD", "--amount", "-3"],
        ["USD", "--amount", "lots"],
        ["USD", "--date", "2026-10-01", "--start", "2026-09-01"],
        ["USD", "--date", "2026-10-01", "--end", "2026-10-02"],
        ["USD", "--group", "week"],
        ["USD", "--start", "2026-01-01", "--group", "day"],
    ])
    def test_invalid_exits_2(self, argv):
        with pytest.raises(SystemExit) as exc:
            fx.parse_args(argv)
        assert exc.value.code == 2


class TestMain:
    def _wire(self, monkeypatch, payload, calls=None):
        def fake_fetch(params):
            if calls is not None:
                calls.append(params)
            return payload

        monkeypatch.setattr(fx, "fetch_rates", fake_fetch)
        monkeypatch.setattr(daily_prices.dt, "date", _FixedDate)

    def test_json_latest_uppercases_codes(self, monkeypatch, capsys):
        calls = []
        self._wire(monkeypatch, [_record("2026-10-27", "EUR", 0.89237)], calls)
        fx.main(["usd", "eur", "--json"])
        assert calls == [{"base": "USD", "quotes": "EUR"}]
        payload = json.loads(capsys.readouterr().out)
        assert payload["base"] == "USD" and payload["quotes"] == ["EUR"]
        assert payload["amount"] == 1.0 and payload["date"] is None
        assert payload["source"] == fx.SOURCE
        assert payload["rates"] == [{"date": "2026-10-27", "quote": "EUR",
                                     "rate": 0.89237, "converted": 0.89237}]

    def test_text_single_date_with_amount(self, monkeypatch, capsys):
        calls = []
        self._wire(monkeypatch, [_record("2026-10-24", "SGD", 1.2775)], calls)
        fx.main(["USD", "SGD", "--amount", "250", "--date", "2026-10-24"])
        assert calls[0]["date"] == "2026-10-24"
        out = capsys.readouterr().out
        assert "USD exchange rates - on 2026-10-24" in out
        assert "2026-10-24  250 USD = 319.3750 SGD  (rate 1.2775)" in out
        assert out.rstrip().endswith(f"Source: {fx.SOURCE}")

    def test_text_latest_in_code_order_with_own_dates(self, monkeypatch, capsys):
        self._wire(monkeypatch, [_record("2026-10-23", "BTC", 1.2272e-05),
                                 _record("2026-10-27", "AED", 3.6725)])
        fx.main(["USD"])
        lines = capsys.readouterr().out.splitlines()
        assert lines[2] == "2026-10-27  1 USD = 3.6725 AED"
        assert lines[3] == "2026-10-23  1 USD = 0.00001227 BTC"

    def test_range_table_and_end_defaults_to_today(self, monkeypatch, capsys):
        calls = []
        self._wire(monkeypatch, [
            _record("2026-10-19", "USD", 1.1233, "EUR"), _record("2026-10-19", "GBP", 0.8427, "EUR"),
            _record("2026-10-20", "USD", 1.1228, "EUR"),
        ], calls)
        fx.main(["EUR", "USD", "GBP", "--start", "2026-10-19", "--group", "week"])
        assert calls[0]["from"] == "2026-10-19" and calls[0]["to"] == "2026-10-21"
        assert calls[0]["group"] == "week"
        out = capsys.readouterr().out
        assert "EUR exchange rates - from 2026-10-19 to 2026-10-21 (one rate per week)" in out
        assert "1 EUR in each currency:" in out
        assert "2026-10-19          0.8427        1.1233" in out
        assert "2026-10-20               -        1.1228" in out

    def test_no_rates_text(self, monkeypatch, capsys):
        self._wire(monkeypatch, [])
        fx.main(["USD", "EUR", "--date", "1900-01-01"])
        out = capsys.readouterr().out
        assert "No USD rates found for EUR on 1900-01-01." in out

    def test_no_rates_json(self, monkeypatch, capsys):
        self._wire(monkeypatch, [])
        fx.main(["USD", "--date", "1900-01-01", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["rates"] == [] and payload["date"] == "1900-01-01"

    def test_fetch_error_exits_1(self, monkeypatch, capsys):
        def boom(params):
            raise requests.HTTPError("HTTP 422: invalid currency: ZZZ")

        monkeypatch.setattr(fx, "fetch_rates", boom)
        with pytest.raises(SystemExit) as exc:
            fx.main(["USD", "ZZZ", "--json"])
        assert exc.value.code == 1
        error = json.loads(capsys.readouterr().err)["error"]
        assert error == "failed to fetch exchange rates for USD: HTTP 422: invalid currency: ZZZ"

    def test_fetch_error_text(self, monkeypatch, capsys):
        def boom(params):
            raise requests.ConnectionError("no route")

        monkeypatch.setattr(fx, "fetch_rates", boom)
        with pytest.raises(SystemExit) as exc:
            fx.main(["USD"])
        assert exc.value.code == 1
        assert capsys.readouterr().err.startswith("Error: failed to fetch exchange rates for USD")

    @pytest.mark.parametrize("argv, message", [
        (["USD", "--date", "2026-13-01"], "invalid date"),
        (["USD", "--start", "not-a-date"], "invalid date"),
        (["USD", "--end", "2026-10-01"], "--end requires --start"),
        (["USD", "--start", "2026-10-10", "--end", "2026-10-01"], "is before start date"),
    ])
    def test_bad_dates_exit_1_before_fetch(self, monkeypatch, capsys, argv, message):
        monkeypatch.setattr(fx, "fetch_rates", lambda params: pytest.fail("fetched"))
        with pytest.raises(SystemExit) as exc:
            fx.main(argv + ["--json"])
        assert exc.value.code == 1
        assert message in json.loads(capsys.readouterr().err)["error"]


class _FixedDate(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)
