"""Tests for stock_earnings_calendar: calendar extraction, output, main()."""

import datetime as dt
import json

import pytest
import requests

import stock_earnings_calendar as sec
import yahoo_finance as yf

TODAY = dt.date(2026, 10, 15)


def _ts(text):
    """'YYYY-MM-DD[ HH:MM]' (UTC) -> epoch seconds."""
    fmt = "%Y-%m-%d %H:%M" if " " in text else "%Y-%m-%d"
    return int(dt.datetime.strptime(text, fmt).replace(tzinfo=dt.timezone.utc).timestamp())


def _history_entry(quarter, estimate, actual, surprise):
    return {"quarter": {"raw": _ts(quarter), "fmt": quarter},
            "epsEstimate": {"raw": estimate}, "epsActual": {"raw": actual},
            "surprisePercent": {"raw": surprise}, "currency": "USD"}


def _modules():
    """Minimal quoteSummary ``modules`` with every field the calendar reads."""
    return {
        "price": {"longName": "Triple A Inc.", "currency": "USD", "exchangeName": "TST"},
        "financialData": {"financialCurrency": "USD"},
        "defaultKeyStatistics": {"lastDividendValue": {"raw": 0.27},
                                 "lastDividendDate": {"raw": _ts("2026-08-10")}},
        "calendarEvents": {
            "earnings": {
                "earningsDate": [_ts("2026-11-02 20:00")],
                "isEarningsDateEstimate": False,
                "earningsLow": 1.93, "earningsAverage": 1.98, "earningsHigh": 2.07,
                "revenueLow": 112e9, "revenueAverage": 113.6e9, "revenueHigh": 117e9,
            },
            "exDividendDate": _ts("2026-08-10"),
            "dividendDate": _ts("2026-10-20"),
        },
        "earningsHistory": {"history": [
            # Out of order on purpose: the extractor sorts oldest first.
            _history_entry("2026-06-30", 1.89, 2.02, 0.0674),
            _history_entry("2026-03-31", 1.94, 2.01, 0.0346),
        ]},
        "earnings": {"earningsChart": {"quarterly": [
            {"fiscalQuarter": "2Q2026", "periodEndDate": _ts("2026-03-31"),
             "reportedDate": _ts("2026-04-30 20:30")},
            {"fiscalQuarter": "3Q2026", "periodEndDate": _ts("2026-06-30"),
             "reportedDate": _ts("2026-07-30 20:30")},
        ]}},
    }


class TestNextEarnings:
    def test_confirmed_date(self):
        nxt = sec.next_earnings(_modules(), TODAY)
        assert nxt["date"] == nxt["date_end"] == "2026-11-02"
        assert nxt["datetime_utc"] == "2026-11-02T20:00Z"
        assert (nxt["is_estimate"], nxt["status"]) == (False, "upcoming")
        assert nxt["eps_estimate"] == {"low": 1.93, "average": 1.98, "high": 2.07}
        assert nxt["revenue_estimate"]["average"] == 113.6e9

    def test_two_timestamps_are_an_estimated_window(self):
        modules = _modules()
        modules["calendarEvents"]["earnings"]["earningsDate"] = [
            _ts("2026-11-09"), _ts("2026-11-02")]
        nxt = sec.next_earnings(modules, TODAY)
        assert (nxt["date"], nxt["date_end"]) == ("2026-11-02", "2026-11-09")
        assert nxt["is_estimate"] is True

    def test_past_date_flagged(self):
        nxt = sec.next_earnings(_modules(), dt.date(2026, 11, 3))
        assert nxt["status"] == "past"

    def test_no_estimates_gives_none(self):
        modules = _modules()
        modules["calendarEvents"]["earnings"] = {"earningsDate": [_ts("2026-11-02")]}
        nxt = sec.next_earnings(modules, TODAY)
        assert nxt["eps_estimate"] is None and nxt["revenue_estimate"] is None

    @pytest.mark.parametrize("calendar", [{}, {"earnings": {}}, {"earnings": {"earningsDate": []}}])
    def test_no_date_returns_none(self, calendar):
        assert sec.next_earnings({"calendarEvents": calendar}, TODAY) is None


class TestDividendDates:
    def test_dates_status_and_amount(self):
        div = sec.dividend_dates(_modules(), TODAY, "USD")
        assert div == {
            "ex_dividend_date": "2026-08-10", "ex_dividend_status": "past",
            "payment_date": "2026-10-20", "payment_status": "upcoming",
            "last_amount": 0.27, "last_amount_date": "2026-08-10", "amount_currency": "USD",
        }

    def test_today_counts_as_upcoming(self):
        div = sec.dividend_dates(_modules(), dt.date(2026, 10, 20), "USD")
        assert div["payment_status"] == "upcoming"

    @pytest.mark.parametrize("currency", ["GBp", "ILA", "ZAc"])
    def test_minor_unit_listing_has_no_amount_currency(self, currency):
        assert sec.dividend_dates(_modules(), TODAY, currency)["amount_currency"] is None

    def test_no_dividend_returns_none(self):
        assert sec.dividend_dates({"calendarEvents": {"earnings": {}}}, TODAY, "USD") is None


class TestEarningsHistory:
    def test_sorted_and_matched_to_chart(self):
        rows = sec.earnings_history(_modules())
        assert [r["quarter_end"] for r in rows] == ["2026-03-31", "2026-06-30"]
        assert rows[1] == {
            "quarter_end": "2026-06-30", "fiscal_quarter": "3Q2026",
            "reported_date": "2026-07-30", "eps_estimate": 1.89, "eps_actual": 2.02,
            "surprise_pct": 0.0674, "currency": "USD",
        }

    def test_unmatched_quarter_has_no_report_date(self):
        modules = _modules()
        modules["earnings"] = {}
        row = sec.earnings_history(modules)[0]
        assert row["fiscal_quarter"] is None and row["reported_date"] is None

    def test_rows_without_eps_dropped(self):
        modules = _modules()
        modules["earningsHistory"]["history"].append({"quarter": {"raw": _ts("2026-09-30")}})
        assert len(sec.earnings_history(modules)) == 2


class TestExtractCalendar:
    def test_reporting_currency_falls_back_to_history_then_price(self):
        modules = _modules()
        del modules["financialData"]
        modules["earningsHistory"]["history"][0]["currency"] = "EUR"
        assert sec.extract_calendar(modules, TODAY)["reporting_currency"] == "EUR"
        modules["earningsHistory"] = {}
        assert sec.extract_calendar(modules, TODAY)["reporting_currency"] == "USD"

    def test_reporting_currency_can_differ_from_trading(self):
        modules = _modules()
        modules["price"]["currency"] = "GBp"
        modules["financialData"]["financialCurrency"] = "EUR"
        calendar = sec.extract_calendar(modules, TODAY)
        assert (calendar["currency"], calendar["reporting_currency"]) == ("GBp", "EUR")


class TestBuildReport:
    def test_sections(self):
        report = sec.build_report("AAA", sec.extract_calendar(_modules(), TODAY))
        lines = report.splitlines()
        assert lines[0] == "AAA - Triple A Inc.  (TST - USD)"
        assert "2026-11-02 20:00 UTC  (confirmed, upcoming)" in report
        assert "1.98  (range 1.93 - 2.07) USD" in report
        assert "2026-08-10  (past)" in report
        assert "0.27 USD  (ex-date 2026-08-10)" in report
        assert "+6.74%" in report

    def test_estimated_window_and_missing_sections(self):
        modules = _modules()
        modules["calendarEvents"] = {"earnings": {
            "earningsDate": [_ts("2026-11-02"), _ts("2026-11-09")]}}
        modules["defaultKeyStatistics"] = {}
        modules["earningsHistory"] = {}
        report = sec.build_report("AAA", sec.extract_calendar(modules, TODAY))
        assert "2026-11-02 to 2026-11-09  (estimated, upcoming)" in report
        assert "EPS estimate       -\n" in report
        assert "No dividend dates from Yahoo" in report
        assert "No past quarters from Yahoo" in report

    def test_small_minor_unit_dividend_keeps_precision(self):
        modules = _modules()
        modules["price"]["currency"] = "GBp"
        modules["defaultKeyStatistics"]["lastDividendValue"] = {"raw": 0.023625}
        report = sec.build_report("AAA", sec.extract_calendar(modules, TODAY))
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
        monkeypatch.setattr(yf, "fetch_quote_summary",
                            lambda s, m: seen.append((s, m)) or _modules())
        sec.main(["aaa", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert seen == [("aaa", sec.MODULES)]
        assert out["symbol"] == "AAA"  # upper-cased
        assert out["next_earnings"]["date"] == "2026-11-02"
        assert len(out["earnings_history"]) == 2

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(yf, "fetch_quote_summary", lambda s, m: _modules())
        sec.main(["AAA"])
        assert "Next earnings" in capsys.readouterr().out

    def test_fetch_error_exits_1_json(self, monkeypatch, capsys):
        def boom(symbol, modules):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(yf, "fetch_quote_summary", boom)
        with pytest.raises(SystemExit) as exc:
            sec.main(["ZZZ", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "failed to fetch earnings calendar for 'ZZZ': Quote not found"}

    def test_no_earnings_data_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(yf, "fetch_quote_summary",
                            lambda s, m: {"price": {"currency": "USD"}})
        with pytest.raises(SystemExit) as exc:
            sec.main(["SPY"])
        assert exc.value.code == 1
        assert "no earnings data for 'SPY'" in capsys.readouterr().err

    def test_unknown_flag_exits_2_before_fetch(self, monkeypatch):
        monkeypatch.setattr(yf, "fetch_quote_summary",
                            lambda s, m: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            sec.main(["AAA", "--bogus"])
        assert exc.value.code == 2
