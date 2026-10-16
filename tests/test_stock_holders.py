"""Tests for stock_holders: classification, extraction, output and main()."""

import json
import time

import pytest
import requests

import stock_holders as sh
import yahoo_finance as yf

DAY = 86400
NOW = 1_790_000_000  # 2026-09-21 14:13 UTC


def _tx(days_ago, name, relation, text, shares=1000, value=0, ownership="D", now=NOW):
    return {"startDate": {"raw": int(now - days_ago * DAY)}, "filerName": name,
            "filerRelation": relation, "transactionText": text,
            "shares": {"raw": shares}, "value": {"raw": value}, "ownership": ownership}


def _holder(name, pct, shares, change, report=NOW - 60 * DAY):
    return {"organization": name, "pctHeld": {"raw": pct}, "position": {"raw": shares},
            "value": {"raw": shares * 10}, "pctChange": {"raw": change},
            "reportDate": {"raw": int(report)}}


def _modules(now=NOW):
    return {
        "price": {"longName": "Triple A Inc.", "shortName": "Triple A Inc", "currency": "USD",
                  "exchangeName": "TST"},
        "majorHoldersBreakdown": {"insidersPercentHeld": 0.02, "institutionsPercentHeld": 0.6,
                                  "institutionsFloatPercentHeld": 0.61, "institutionsCount": 900},
        "insiderTransactions": {"transactions": [
            # Out of order on purpose; one outside the default 180 days.
            _tx(30, "DOE JANE", "Director", "Sale at price 10.00 - 12.00 per share.",
                2000, 22000, now=now),
            _tx(5, "ROE RICHARD", "Chief Executive Officer", "Sale at price 11.50 per share.",
                1000, 11500, "I", now=now),
            _tx(10, "DOE JANE", "Director", "Purchase at price 9.00 per share.", 500, 4500, now=now),
            _tx(12, "ROE RICHARD", "Chief Executive Officer", "Stock Award(Grant) at price 0.00 per share.",
                3000, now=now),
            _tx(15, "POE PAT", "Officer", "", 400, now=now),
            _tx(400, "OLD OLIVER", "Director", "Sale at price 5.00 per share.", 10, 50, now=now),
        ]},
        "fundOwnership": {"ownershipList": [_holder("Index Fund", 0.03, 3_000_000, 0.01)]},
        "institutionOwnership": {"ownershipList": [_holder("Big Asset Co", 0.08, 8_000_000, -0.02)]},
    }


class TestClassify:
    @pytest.mark.parametrize("text, kind", [
        ("Sale at price 222.19 - 223.75 per share.", "sale"),
        ("Sold at price 1.70 per share.", "sale"),
        ("Purchase at price 9.00 per share.", "purchase"),
        ("Bought at price 1.58 per share.", "purchase"),
        ("Buy Back at price 1.20 per share.", "buyback"),
        ("Conversion of Exercise of derivative security at price 0.00 per share.", "option_exercise"),
        ("Stock Award(Grant) at price 0.00 per share.", "award"),
        ("Stock Gift at price 0.00 per share.", "gift"),
        ("Other at price 44.41 per share.", "other"),
        ("Decrease", "other"),
    ])
    def test_by_description(self, text, kind):
        assert sh.classify(text, "SOMEONE", "Director", ["Acme Corp"]) == kind

    def test_description_wins_without_a_role(self):
        # Vodafone's directors' trades come with no role filled in.
        assert sh.classify("Bought at price 1.58 per share.", "Carter (Stephen A.)", None,
                           ["Vodafone Group Public Limited Company"]) == "purchase"

    def test_blank_from_the_company_is_a_buyback(self):
        names = ["Vodafone Group Public Limited Company", "VODAFONE GROUP PLC ORD USD0.20"]
        assert sh.classify("", "Vodafone Group Plc", None, names) == "buyback"
        assert sh.classify(None, "Toyota Motor Corp", None, ["Toyota Motor Corporation"]) == "buyback"

    def test_blank_without_role_is_a_holder_disclosure(self):
        assert sh.classify("", "Societe Generale S.A", None, ["Vodafone Group Plc"]) == "holder_disclosure"

    def test_blank_with_role_is_unspecified(self):
        assert sh.classify("", "COOK TIMOTHY D", "Officer and Director", ["Apple Inc."]) == "unspecified"


class TestHelpers:
    @pytest.mark.parametrize("symbol, us", [
        ("AAPL", True), ("BRK-B", True), ("VOD.L", False), ("7203.T", False), ("D05.SI", False),
    ])
    def test_us_listing(self, symbol, us):
        assert sh.is_us_listing(symbol) is us

    @pytest.mark.parametrize("text, expected", [
        ("Sale at price 222.19 - 223.75 per share.", (222.19, 223.75)),
        ("Sale at price 1,234.50 per share.", (1234.5, 1234.5)),
        ("Stock Gift at price 0.00 per share.", (None, None)),
        ("", (None, None)),
        (None, (None, None)),
    ])
    def test_price_range(self, text, expected):
        assert sh._price_range(text) == expected


class TestInsiderTransactions:
    def test_window_and_newest_first(self):
        rows = sh.insider_transactions(_modules(), ["Triple A Inc."], 180, now=NOW)
        assert [r["date"] for r in rows] == [
            "2026-09-16", "2026-09-11", "2026-09-09", "2026-09-06", "2026-08-22"]
        assert "OLD OLIVER" not in [r["name"] for r in rows]

    def test_fields(self):
        rows = sh.insider_transactions(_modules(), ["Triple A Inc."], 180, now=NOW)
        assert rows[0] == {
            "date": "2026-09-16", "name": "ROE RICHARD", "relation": "Chief Executive Officer",
            "kind": "sale", "text": "Sale at price 11.50 per share.", "shares": 1000,
            "value": 11500.0, "price_low": 11.5, "price_high": 11.5, "ownership": "indirect",
        }
        award = next(r for r in rows if r["kind"] == "award")
        assert (award["value"], award["price_low"]) == (None, None)  # Yahoo's 0 placeholders

    def test_days_narrows_window(self):
        rows = sh.insider_transactions(_modules(), [], 7, now=NOW)
        assert [r["name"] for r in rows] == ["ROE RICHARD"]

    def test_undated_entries_skipped(self):
        modules = {"insiderTransactions": {"transactions": [{"filerName": "X"}]}}
        assert sh.insider_transactions(modules, [], 180, now=NOW) == []

    def test_missing_module(self):
        assert sh.insider_transactions({}, [], now=NOW) == []


class TestInsiderSummary:
    def test_sales_and_purchases_apart_from_the_rest(self):
        rows = sh.insider_transactions(_modules(), ["Triple A Inc."], 180, now=NOW)
        summary = sh.insider_summary(rows)
        assert summary["sales"] == {"count": 2, "shares": 3000, "value": 33500.0}
        assert summary["purchases"] == {"count": 1, "shares": 500, "value": 4500.0}
        assert summary["other_counts"] == {"award": 1, "unspecified": 1}

    def test_by_insider_most_value_first(self):
        rows = sh.insider_transactions(_modules(), ["Triple A Inc."], 180, now=NOW)
        assert sh.insider_summary(rows)["by_insider"] == [
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
    def test_us_listing(self):
        data = sh.extract_holders("AAA", _modules(), now=NOW)
        assert data["name"] == "Triple A Inc."
        assert data["us_listing"] is True
        assert data["ownership"] == {"insiders_pct": 0.02, "institutions_pct": 0.6,
                                     "institutions_float_pct": 0.61, "institutions_count": 900}
        assert data["days"] == 180
        assert len(data["transactions"]) == 5
        assert data["top_funds"] == [{"name": "Index Fund", "pct_held": 0.03, "shares": 3_000_000,
                                      "value": 30_000_000.0, "pct_change": 0.01,
                                      "report_date": "2026-07-23"}]
        assert data["top_institutions"][0]["name"] == "Big Asset Co"

    def test_non_us_listing_hides_institutions(self):
        data = sh.extract_holders("AAA.L", _modules(), now=NOW)
        assert data["us_listing"] is False
        assert data["top_institutions"] is None
        assert data["top_funds"]

    def test_transaction_currency(self):
        assert sh.extract_holders("AAA", _modules(), now=NOW)["transaction_currency"] == "USD"
        modules = _modules()
        modules["price"]["currency"] = "GBp"
        assert sh.extract_holders("AAA.L", modules, now=NOW)["transaction_currency"] == "USD"
        modules["price"]["currency"] = "CAD"  # a US-listed stock quoted in another currency
        assert sh.extract_holders("AAA", modules, now=NOW)["transaction_currency"] == "CAD"
        assert sh.extract_holders("AAA", {}, now=NOW)["transaction_currency"] is None

    def test_trades_only_filters_list_not_summary(self):
        data = sh.extract_holders("AAA", _modules(), now=NOW, trades_only=True)
        assert data["trades_only"] is True
        assert [t["kind"] for t in data["transactions"]] == ["sale", "purchase", "sale"]
        assert data["insider_summary"]["other_counts"] == {"award": 1, "unspecified": 1}
        assert sh.transaction_count(data) == 5

    def test_trades_only_keeps_option_exercises(self):
        modules = {"insiderTransactions": {"transactions": [
            _tx(3, "X", "Officer", "Conversion of Exercise of derivative security at price 0.00 per share."),
            _tx(4, "X", "Officer", "Stock Gift at price 0.00 per share."),
        ]}}
        data = sh.extract_holders("AAA", modules, now=NOW, trades_only=True)
        assert [t["kind"] for t in data["transactions"]] == ["option_exercise"]

    def test_has_data_counts_transactions_left_out_by_trades_only(self):
        modules = {"insiderTransactions": {"transactions": [
            _tx(3, "Acme Corp", None, "Buy Back at price 1.20 per share.")]}}
        data = sh.extract_holders("ACME.L", modules, now=NOW, trades_only=True)
        assert data["transactions"] == []
        assert sh.has_data(data)

    def test_has_data(self):
        assert sh.has_data(sh.extract_holders("AAA", _modules(), now=NOW))
        assert not sh.has_data(sh.extract_holders("SPY", {"price": {"currency": "USD"}}, now=NOW))
        funds_only = {"fundOwnership": _modules()["fundOwnership"]}
        assert sh.has_data(sh.extract_holders("AAA.L", funds_only, now=NOW))


class TestBuildReport:
    def test_sections(self):
        report = sh.build_report("AAA", sh.extract_holders("AAA", _modules(), now=NOW))
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
        report = sh.build_report("AAA", sh.extract_holders("AAA", _modules(), now=NOW))
        lines = report.splitlines()
        start = next(i for i, line in enumerate(lines) if "By insider" in line)
        assert "DOE JANE" in lines[start + 1] and "22,000.00" in lines[start + 1] and "4,500.00" in lines[start + 1]
        assert "ROE RICHARD" in lines[start + 2]
        assert "--trades-only" not in report

    def test_by_insider_capped(self, monkeypatch):
        monkeypatch.setattr(sh, "BY_INSIDER_TO_SHOW", 1)
        report = sh.build_report("AAA", sh.extract_holders("AAA", _modules(), now=NOW))
        assert "... and 1 more" in report

    def test_trades_only_report(self):
        report = sh.build_report("AAA", sh.extract_holders("AAA", _modules(), now=NOW, trades_only=True))
        assert "Showing sales, purchases and option exercises only (--trades-only)" in report
        assert "Other      1 award, 1 unspecified" in report  # summary still counts them
        assert "POE PAT" not in report

    def test_trades_only_with_no_trades(self):
        modules = {"insiderTransactions": {"transactions": [
            _tx(3, "Acme Corp", None, "Buy Back at price 1.20 per share.")]}}
        report = sh.build_report("ACME.L", sh.extract_holders("ACME.L", modules, now=NOW, trades_only=True))
        assert "Other      1 buyback" in report
        assert "No sales, purchases or option exercises in the window" in report
        assert "No insider transactions from Yahoo" not in report

    def test_non_us_notes(self):
        report = sh.build_report("AAA.L", sh.extract_holders("AAA.L", _modules(), now=NOW))
        assert "not shown for non-US listings" in report
        assert "Big Asset Co" not in report
        assert "large-holder disclosures" in report
        assert "appear to be in USD, not USD" in report  # the fixture's quote currency is USD

    def test_no_transactions_and_no_holders(self):
        modules = {"majorHoldersBreakdown": _modules()["majorHoldersBreakdown"]}
        report = sh.build_report("AAA", sh.extract_holders("AAA", modules, 30, now=NOW))
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
        modules = _modules(now=time.time())
        monkeypatch.setattr(yf, "fetch_quote_summary", lambda s, m: seen.append((s, m)) or modules)
        sh.main(["aaa", "--days", "20", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert seen == [("aaa", sh.MODULES)]
        assert out["symbol"] == "AAA"
        assert out["days"] == 20
        assert [t["name"] for t in out["transactions"]] == ["ROE RICHARD", "DOE JANE", "ROE RICHARD", "POE PAT"]

    def test_trades_only_json(self, monkeypatch, capsys):
        monkeypatch.setattr(yf, "fetch_quote_summary", lambda s, m: _modules(now=time.time()))
        sh.main(["AAA", "--trades-only", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert out["trades_only"] is True
        assert {t["kind"] for t in out["transactions"]} == {"sale", "purchase"}
        assert out["insider_summary"]["by_insider"][0]["name"] == "DOE JANE"

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(yf, "fetch_quote_summary", lambda s, m: _modules(now=time.time()))
        sh.main(["AAA"])
        assert "Insider activity" in capsys.readouterr().out

    def test_fetch_error_exits_1_json(self, monkeypatch, capsys):
        def boom(symbol, modules):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(yf, "fetch_quote_summary", boom)
        with pytest.raises(SystemExit) as exc:
            sh.main(["ZZZ", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "failed to fetch holders for 'ZZZ': Quote not found"}

    def test_no_data_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(yf, "fetch_quote_summary", lambda s, m: {"price": {"currency": "USD"}})
        with pytest.raises(SystemExit) as exc:
            sh.main(["SPY"])
        assert exc.value.code == 1
        assert "no ownership data for 'SPY'" in capsys.readouterr().err

    def test_unknown_flag_exits_2_before_fetch(self, monkeypatch):
        monkeypatch.setattr(yf, "fetch_quote_summary", lambda s, m: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            sh.main(["AAA", "--bogus"])
        assert exc.value.code == 2
