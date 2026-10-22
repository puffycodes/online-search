"""Tests for stock_holders: shaping stock_data's holders view, output and main().

The Yahoo parsing behind stock_data.holders_view() (transaction kinds, prices,
the --days window, holder lists) is tested in test_yahoo_finance.py; here every
view is already in stock_data's neutral shape.
"""

import json

import pytest
import requests

import stock_data
import stock_holders as sh


def _tx(date, name, relation, kind, text, shares=1000, value=None, low=None, high=None,
        ownership="direct"):
    return {"date": date, "name": name, "relation": relation, "kind": kind, "text": text,
            "shares": shares, "value": value, "price_low": low, "price_high": high,
            "ownership": ownership}


def _transactions():
    """Five transactions, newest first, as stock_data returns them."""
    return [
        _tx("2026-09-16", "ROE RICHARD", "Chief Executive Officer", "sale",
            "Sale at price 11.50 per share.", 1000, 11500.0, 11.5, 11.5, "indirect"),
        _tx("2026-09-11", "DOE JANE", "Director", "purchase",
            "Purchase at price 9.00 per share.", 500, 4500.0, 9.0, 9.0),
        _tx("2026-09-09", "ROE RICHARD", "Chief Executive Officer", "award",
            "Stock Award(Grant) at price 0.00 per share.", 3000),
        _tx("2026-09-06", "POE PAT", "Officer", "unspecified", None, 400),
        _tx("2026-08-22", "DOE JANE", "Director", "sale",
            "Sale at price 10.00 - 12.00 per share.", 2000, 22000.0, 10.0, 12.0),
    ]


def _holder(name, pct, shares, change):
    return {"name": name, "pct_held": pct, "shares": shares, "value": shares * 10.0,
            "pct_change": change, "report_date": "2026-07-23"}


def _view(us=True, currency="USD", transactions=None):
    """A neutral holders view with every field filled in."""
    return {
        "source": "Test", "notes": [],
        "name": "Triple A Inc.", "exchange": "TST", "currency": currency,
        "us_listing": us,
        "transaction_currency": currency if us else "USD",
        "ownership": {"insiders_pct": 0.02, "institutions_pct": 0.6,
                      "institutions_float_pct": 0.61, "institutions_count": 900},
        "transactions": _transactions() if transactions is None else transactions,
        "top_funds": [_holder("Index Fund", 0.03, 3_000_000, 0.01)],
        "top_institutions": [_holder("Big Asset Co", 0.08, 8_000_000, -0.02)] if us else None,
    }


def _empty_view(us=True):
    """What a provider returns for an ETF or index: no ownership data at all."""
    return {**_view(us, transactions=[]), "top_funds": [],
            "top_institutions": [] if us else None,
            "ownership": dict.fromkeys(("insiders_pct", "institutions_pct",
                                        "institutions_float_pct", "institutions_count"))}


def _buyback_only():
    return {**_empty_view(us=False), "transactions": [
        _tx("2026-09-18", "Acme Corp", None, "buyback", "Buy Back at price 1.20 per share.")]}


class TestInsiderSummary:
    def test_sales_and_purchases_apart_from_the_rest(self):
        summary = sh.insider_summary(_transactions())
        assert summary["sales"] == {"count": 2, "shares": 3000, "value": 33500.0}
        assert summary["purchases"] == {"count": 1, "shares": 500, "value": 4500.0}
        assert summary["other_counts"] == {"award": 1, "unspecified": 1}

    def test_by_insider_most_value_first(self):
        assert sh.insider_summary(_transactions())["by_insider"] == [
            {"name": "DOE JANE", "relation": "Director",
             "sales": {"count": 1, "shares": 2000, "value": 22000.0},
             "purchases": {"count": 1, "shares": 500, "value": 4500.0}},
            {"name": "ROE RICHARD", "relation": "Chief Executive Officer",
             "sales": {"count": 1, "shares": 1000, "value": 11500.0},
             "purchases": {"count": 0, "shares": 0, "value": 0}},
        ]  # POE PAT (unspecified only) and the award don't make anyone a trader

    def test_by_insider_ties_broken_by_shares_and_missing_roles_filled(self):
        rows = [
            {"name": "A", "relation": None, "kind": "sale", "shares": 10, "value": None},
            {"name": "B", "relation": None, "kind": "sale", "shares": 50, "value": None},
            {"name": "B", "relation": "Director", "kind": "purchase", "shares": 5, "value": None},
            {"name": None, "relation": None, "kind": "sale", "shares": 99, "value": None},
        ]
        by_insider = sh.insider_summary(rows)["by_insider"]
        assert [(p["name"], p["relation"]) for p in by_insider] == [("B", "Director"), ("A", None)]

    def test_empty(self):
        summary = sh.insider_summary([])
        assert summary["sales"] == {"count": 0, "shares": 0, "value": 0}
        assert summary["by_insider"] == []


class TestExtractHolders:
    def test_fields_passed_through(self):
        data = sh.extract_holders(_view(), 180)
        assert data["name"] == "Triple A Inc."
        assert (data["us_listing"], data["transaction_currency"]) == (True, "USD")
        assert data["ownership"]["institutions_count"] == 900
        assert (data["days"], data["trades_only"]) == (180, False)
        assert len(data["transactions"]) == 5
        assert data["top_funds"][0]["name"] == "Index Fund"
        assert data["top_institutions"][0]["name"] == "Big Asset Co"

    def test_json_key_order(self):
        assert list(sh.extract_holders(_view())) == [
            "name", "exchange", "currency", "us_listing", "transaction_currency", "ownership",
            "days", "trades_only", "insider_summary", "transactions", "top_funds",
            "top_institutions"]

    def test_non_us_listing(self):
        data = sh.extract_holders(_view(us=False, currency="GBp"))
        assert (data["us_listing"], data["transaction_currency"]) == (False, "USD")
        assert data["top_institutions"] is None
        assert data["top_funds"]

    def test_trades_only_filters_list_not_summary(self):
        data = sh.extract_holders(_view(), trades_only=True)
        assert data["trades_only"] is True
        assert [t["kind"] for t in data["transactions"]] == ["sale", "purchase", "sale"]
        assert data["insider_summary"]["other_counts"] == {"award": 1, "unspecified": 1}
        assert sh.transaction_count(data) == 5

    def test_trades_only_keeps_option_exercises(self):
        view = _view(transactions=[
            _tx("2026-09-18", "X", "Officer", "option_exercise",
                "Conversion of Exercise of derivative security at price 0.00 per share."),
            _tx("2026-09-17", "X", "Officer", "gift", "Stock Gift at price 0.00 per share."),
        ])
        data = sh.extract_holders(view, trades_only=True)
        assert [t["kind"] for t in data["transactions"]] == ["option_exercise"]

    def test_has_data_counts_transactions_left_out_by_trades_only(self):
        data = sh.extract_holders(_buyback_only(), trades_only=True)
        assert data["transactions"] == []
        assert sh.has_data(data)

    def test_has_data(self):
        assert sh.has_data(sh.extract_holders(_view()))
        assert not sh.has_data(sh.extract_holders(_empty_view()))
        funds_only = {**_empty_view(us=False), "top_funds": _view()["top_funds"]}
        assert sh.has_data(sh.extract_holders(funds_only))


class TestBuildReport:
    def test_sections(self):
        report = sh.build_report("AAA", sh.extract_holders(_view()))
        assert report.splitlines()[0] == "AAA - Triple A Inc.  (TST - USD)"
        assert "insiders 2.00%" in report and "institutions 60.00% (61.00% of float)" in report
        assert "900 institutions" in report
        assert "Insider activity (last 180 days)" in report
        assert "Other      1 award, 1 unspecified" in report
        sale = next(line for line in report.splitlines() if "DOE JANE" in line and "sale" in line)
        assert "10.00-12.00" in sale and "22,000.00" in sale
        assert "Top funds" in report and "Index Fund" in report and "+1.00%" in report
        assert "Top institutions" in report and "Big Asset Co" in report and "-2.00%" in report
        assert "large-holder disclosures" not in report

    def test_by_insider_section(self):
        lines = sh.build_report("AAA", sh.extract_holders(_view())).splitlines()
        start = next(i for i, line in enumerate(lines) if "By insider" in line)
        assert "DOE JANE" in lines[start + 1] and "22,000.00" in lines[start + 1] and "4,500.00" in lines[start + 1]
        assert "ROE RICHARD" in lines[start + 2]
        assert not any("--trades-only" in line for line in lines)

    def test_by_insider_capped(self, monkeypatch):
        monkeypatch.setattr(sh, "BY_INSIDER_TO_SHOW", 1)
        assert "... and 1 more" in sh.build_report("AAA", sh.extract_holders(_view()))

    def test_trades_only_report(self):
        report = sh.build_report("AAA", sh.extract_holders(_view(), trades_only=True))
        assert "Showing sales, purchases and option exercises only (--trades-only)" in report
        assert "Other      1 award, 1 unspecified" in report  # summary still counts them
        assert "POE PAT" not in report

    def test_trades_only_with_no_trades(self):
        report = sh.build_report("ACME.L", sh.extract_holders(_buyback_only(), trades_only=True))
        assert "Other      1 buyback" in report
        assert "No sales, purchases or option exercises in the window" in report
        assert "No insider transactions from Yahoo" not in report

    def test_non_us_notes(self):
        report = sh.build_report("AAA.L", sh.extract_holders(_view(us=False)))
        assert "not shown for non-US listings" in report
        assert "Big Asset Co" not in report
        assert "large-holder disclosures" in report
        assert "appear to be in USD, not USD" in report  # the fixture's quote currency is USD

    def test_no_transactions_and_no_holders(self):
        view = {**_empty_view(), "ownership": _view()["ownership"]}
        report = sh.build_report("AAA", sh.extract_holders(view, 30))
        assert "No insider transactions from Yahoo in the last 30 days" in report
        assert report.count("None reported by Yahoo") == 2


class TestParseArgs:
    def test_defaults(self):
        args = sh.parse_args(["AAPL"])
        assert (args.symbol, args.days, args.trades_only, args.json) == ("AAPL", 180, False, False)

    def test_trades_only_flag(self):
        assert sh.parse_args(["AAPL", "--trades-only"]).trades_only is True

    @pytest.mark.parametrize("argv", [[], ["AAPL", "--days", "0"], ["AAPL", "--days", "x"]])
    def test_invalid_exits_2(self, argv):
        with pytest.raises(SystemExit) as exc:
            sh.parse_args(argv)
        assert exc.value.code == 2


class TestMain:
    def test_json_output(self, monkeypatch, capsys):
        seen = []
        monkeypatch.setattr(stock_data, "holders_view",
                            lambda s, d: seen.append((s, d)) or _view(transactions=_transactions()[:4]))
        sh.main(["aaa", "--days", "20", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert seen == [("aaa", 20)]
        assert out["symbol"] == "AAA"
        assert out["days"] == 20
        assert [t["name"] for t in out["transactions"]] == ["ROE RICHARD", "DOE JANE", "ROE RICHARD", "POE PAT"]
        assert "source" not in out and "notes" not in out

    def test_trades_only_json(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "holders_view", lambda s, d: _view())
        sh.main(["AAA", "--trades-only", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert out["trades_only"] is True
        assert {t["kind"] for t in out["transactions"]} == {"sale", "purchase"}
        assert out["insider_summary"]["by_insider"][0]["name"] == "DOE JANE"

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "holders_view", lambda s, d: _view())
        sh.main(["AAA"])
        assert "Insider activity" in capsys.readouterr().out

    def test_fetch_error_exits_1_json(self, monkeypatch, capsys):
        def boom(symbol, days):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(stock_data, "holders_view", boom)
        with pytest.raises(SystemExit) as exc:
            sh.main(["ZZZ", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "failed to fetch holders for 'ZZZ': Quote not found"}

    def test_no_data_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "holders_view", lambda s, d: _empty_view())
        with pytest.raises(SystemExit) as exc:
            sh.main(["SPY"])
        assert exc.value.code == 1
        assert "no ownership data for 'SPY'" in capsys.readouterr().err

    def test_unknown_flag_exits_2_before_fetch(self, monkeypatch):
        monkeypatch.setattr(stock_data, "holders_view", lambda s, d: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            sh.main(["AAA", "--bogus"])
        assert exc.value.code == 2
