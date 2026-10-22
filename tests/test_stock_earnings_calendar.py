"""Tests for stock_earnings_calendar: shaping stock_data's earnings view, output, main().

The Yahoo parsing behind stock_data.earnings_view() is tested in
test_yahoo_finance.py; here every view is already in stock_data's neutral shape.
"""

import datetime as dt
import json

import pytest
import requests

import stock_data
import stock_earnings_calendar as sec

TODAY = dt.date(2026, 10, 15)


def _next(date="2026-11-02", date_end=None, eps=True):
    return {
        "date": date, "date_end": date_end or date,
        "datetime_utc": f"{date}T20:00Z",
        "is_estimate": date_end is not None,
        "eps_estimate": {"low": 1.93, "average": 1.98, "high": 2.07} if eps else None,
        "revenue_estimate": {"low": 112e9, "average": 113.6e9, "high": 117e9} if eps else None,
    }


def _quarter(quarter_end, fiscal, reported, estimate, actual, surprise):
    return {"quarter_end": quarter_end, "fiscal_quarter": fiscal, "reported_date": reported,
            "eps_estimate": estimate, "eps_actual": actual, "surprise_pct": surprise,
            "currency": "USD"}


def _view(currency="USD"):
    """A neutral earnings view with every field filled in."""
    return {
        "source": "Test", "notes": [],
        "name": "Triple A Inc.", "exchange": "TST", "currency": currency,
        "reporting_currency": "USD",
        "next_earnings": _next(),
        "dividend": {"ex_dividend_date": "2026-08-10", "payment_date": "2026-10-20",
                     "last_amount": 0.27, "last_amount_date": "2026-08-10",
                     "amount_currency": currency},
        "earnings_history": [
            _quarter("2026-03-31", "2Q2026", "2026-04-30", 1.94, 2.01, 0.0346),
            _quarter("2026-06-30", "3Q2026", "2026-07-30", 1.89, 2.02, 0.0674),
        ],
    }


def _empty_view():
    """What a provider returns for an ETF or index: no earnings at all."""
    return {**_view(), "reporting_currency": None, "next_earnings": None,
            "dividend": None, "earnings_history": []}


class TestExtractCalendar:
    def test_next_earnings_gains_status(self):
        nxt = sec.extract_calendar(_view(), TODAY)["next_earnings"]
        assert list(nxt) == ["date", "date_end", "datetime_utc", "is_estimate", "status",
                             "eps_estimate", "revenue_estimate"]
        assert (nxt["date"], nxt["is_estimate"], nxt["status"]) == ("2026-11-02", False, "upcoming")
        assert nxt["eps_estimate"] == {"low": 1.93, "average": 1.98, "high": 2.07}

    def test_past_date_flagged(self):
        nxt = sec.extract_calendar(_view(), dt.date(2026, 11, 3))["next_earnings"]
        assert nxt["status"] == "past"

    def test_dividend_gains_statuses(self):
        div = sec.extract_calendar(_view(), TODAY)["dividend"]
        assert div == {
            "ex_dividend_date": "2026-08-10", "ex_dividend_status": "past",
            "payment_date": "2026-10-20", "payment_status": "upcoming",
            "last_amount": 0.27, "last_amount_date": "2026-08-10", "amount_currency": "USD",
        }

    def test_today_counts_as_upcoming(self):
        div = sec.extract_calendar(_view(), dt.date(2026, 10, 20))["dividend"]
        assert div["payment_status"] == "upcoming"

    def test_missing_dates_have_no_status(self):
        view = _view()
        view["dividend"]["payment_date"] = None
        assert sec.extract_calendar(view, TODAY)["dividend"]["payment_status"] is None

    def test_missing_sections_stay_none(self):
        calendar = sec.extract_calendar(_empty_view(), TODAY)
        assert (calendar["next_earnings"], calendar["dividend"], calendar["earnings_history"]) == (
            None, None, [])

    def test_reporting_currency_falls_back_to_trading(self):
        view = {**_empty_view(), "currency": "GBp"}
        assert sec.extract_calendar(view, TODAY)["reporting_currency"] == "GBp"

    def test_reporting_currency_can_differ_from_trading(self):
        view = {**_view("GBp"), "reporting_currency": "EUR"}
        calendar = sec.extract_calendar(view, TODAY)
        assert (calendar["currency"], calendar["reporting_currency"]) == ("GBp", "EUR")

    def test_json_key_order(self):
        assert list(sec.extract_calendar(_view(), TODAY)) == [
            "name", "exchange", "currency", "reporting_currency", "next_earnings",
            "dividend", "earnings_history"]


class TestBuildReport:
    def test_sections(self):
        report = sec.build_report("AAA", sec.extract_calendar(_view(), TODAY))
        lines = report.splitlines()
        assert lines[0] == "AAA - Triple A Inc.  (TST - USD)"
        assert "2026-11-02 20:00 UTC  (confirmed, upcoming)" in report
        assert "1.98  (range 1.93 - 2.07) USD" in report
        assert "2026-08-10  (past)" in report
        assert "0.27 USD  (ex-date 2026-08-10)" in report
        assert "+6.74%" in report

    def test_estimated_window_and_missing_sections(self):
        view = {**_empty_view(), "next_earnings": _next(date_end="2026-11-09", eps=False)}
        report = sec.build_report("AAA", sec.extract_calendar(view, TODAY))
        assert "2026-11-02 to 2026-11-09  (estimated, upcoming)" in report
        assert "EPS estimate       -\n" in report
        assert "No dividend dates from Yahoo" in report
        assert "No past quarters from Yahoo" in report

    def test_small_minor_unit_dividend_keeps_precision(self):
        view = _view("GBp")
        view["dividend"].update(last_amount=0.023625, amount_currency=None)
        report = sec.build_report("AAA", sec.extract_calendar(view, TODAY))
        assert "0.0236 (currency not stated by Yahoo)" in report


class TestParseArgs:
    def test_defaults(self):
        args = sec.parse_args(["AAPL"])
        assert (args.symbol, args.json) == ("AAPL", False)

    def test_missing_symbol_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            sec.parse_args([])
        assert exc.value.code == 2


class TestMain:
    def test_json_output(self, monkeypatch, capsys):
        seen = []
        monkeypatch.setattr(stock_data, "earnings_view", lambda s: seen.append(s) or _view())
        sec.main(["aaa", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert seen == ["aaa"]
        assert out["symbol"] == "AAA"  # upper-cased
        assert out["next_earnings"]["date"] == "2026-11-02"
        assert len(out["earnings_history"]) == 2
        assert "source" not in out and "notes" not in out

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "earnings_view", lambda s: _view())
        sec.main(["AAA"])
        assert "Next earnings" in capsys.readouterr().out

    def test_fetch_error_exits_1_json(self, monkeypatch, capsys):
        def boom(symbol):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(stock_data, "earnings_view", boom)
        with pytest.raises(SystemExit) as exc:
            sec.main(["ZZZ", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "failed to fetch earnings calendar for 'ZZZ': Quote not found"}

    def test_no_earnings_data_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "earnings_view", lambda s: _empty_view())
        with pytest.raises(SystemExit) as exc:
            sec.main(["SPY"])
        assert exc.value.code == 1
        assert "no earnings data for 'SPY'" in capsys.readouterr().err

    def test_dividend_alone_is_not_earnings_data(self, monkeypatch, capsys):
        view = {**_empty_view(), "dividend": _view()["dividend"]}
        monkeypatch.setattr(stock_data, "earnings_view", lambda s: view)
        with pytest.raises(SystemExit) as exc:
            sec.main(["SPY"])
        assert exc.value.code == 1

    def test_unknown_flag_exits_2_before_fetch(self, monkeypatch):
        monkeypatch.setattr(stock_data, "earnings_view",
                            lambda s: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            sec.main(["AAA", "--bogus"])
        assert exc.value.code == 2
