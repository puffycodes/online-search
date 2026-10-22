"""Tests for stock_analyst_targets: shaping stock_data's analyst view, output, main().

The Yahoo parsing behind stock_data.analyst_view() is tested in
test_yahoo_finance.py; here every view is already in stock_data's neutral shape.
"""

import json

import pytest
import requests

import stock_analyst_targets as sat
import stock_data


def _trend(period, strong_buy, buy, hold, sell, strong_sell):
    return {"period": period, "strong_buy": strong_buy, "buy": buy, "hold": hold,
            "sell": sell, "strong_sell": strong_sell}


def _action(date, firm, action, from_grade, to_grade, target_action=None, target=None,
            prior=None):
    return {"date": date, "firm": firm, "action": action, "from_grade": from_grade,
            "to_grade": to_grade, "target_action": target_action, "target": target,
            "prior_target": prior}


def _actions():
    """Four actions, newest first, as stock_data returns them."""
    return [
        _action("2026-09-19", "Alpha Capital", "upgrade", "Hold", "Buy", "raised", 150.0, 130.0),
        _action("2026-09-11", "Beta Bank", "downgrade", "Buy", "Hold", "lowered", 120.0, 140.0),
        _action("2026-08-22", "Gamma Research", "reiterate", "Neutral", "Neutral"),
        _action("2026-08-07", "Delta Partners", "maintain", "Outperform", "Outperform",
                "maintained", 115.0, 115.0),
    ]


def _view(price=100.0, actions=None):
    """A neutral analyst view with every field filled in."""
    return {
        "source": "Test", "notes": [],
        "name": "Triple A Inc.", "exchange": "TST", "currency": "USD",
        "price": price,
        "analysts": 20,
        "targets": {"low": 80.0, "median": 110.0, "mean": 105.0, "high": 150.0},
        "recommendation": {"key": "buy", "mean": 2.2},
        "trend": [_trend("0m", 6, 10, 4, 1, 1), _trend("-1m", 5, 9, 5, 1, 0)],
        "actions": [] if actions is None else actions,
    }


def _empty_view():
    """What a provider returns for a symbol with no analyst coverage."""
    return {**_view(price=None), "analysts": None,
            "targets": dict.fromkeys(("low", "median", "mean", "high")),
            "recommendation": {"key": None, "mean": None}, "trend": []}


class TestExtractTargets:
    def test_targets_and_upside(self):
        data = sat.extract_targets(_view())
        assert data["price"] == 100.0
        assert data["targets"] == {"low": 80.0, "median": 110.0, "mean": 105.0, "high": 150.0}
        assert data["upside"] == {"low": -0.2, "median": 0.1, "mean": 0.05, "high": 0.5}
        assert data["analysts"] == 20
        assert data["recommendation"] == {"key": "buy", "mean": 2.2}

    def test_no_price_gives_no_upside(self):
        data = sat.extract_targets(_view(price=None))
        assert data["targets"]["high"] == 150.0
        assert set(data["upside"].values()) == {None}

    def test_trend_rows_gain_totals(self):
        rows = sat.extract_targets(_view())["trend"]
        assert rows[0] == {"period": "0m", "strong_buy": 6, "buy": 10, "hold": 4,
                           "sell": 1, "strong_sell": 1, "total": 22}
        assert rows[1]["total"] == 20

    def test_json_key_order(self):
        assert list(sat.extract_targets(_view())) == [
            "name", "exchange", "currency", "price", "analysts", "targets", "upside",
            "recommendation", "trend", "actions_days", "action_summary", "actions"]

    def test_actions_and_summary(self):
        data = sat.extract_targets(_view(actions=_actions()), 90)
        assert data["actions_days"] == 90
        assert [a["firm"] for a in data["actions"]] == [
            "Alpha Capital", "Beta Bank", "Gamma Research", "Delta Partners"]
        assert data["action_summary"] == {
            "upgrades": 1, "downgrades": 1, "initiations": 0,
            "targets_raised": 1, "targets_lowered": 1,
        }


class TestActionSummary:
    def test_counts(self):
        actions = _actions() + [_action("2026-07-01", "Old Firm", "initiate", None, "Buy",
                                        "announced", 90.0)]
        assert sat.action_summary(actions) == {
            "upgrades": 1, "downgrades": 1, "initiations": 1,
            "targets_raised": 1, "targets_lowered": 1,
        }

    def test_none(self):
        assert set(sat.action_summary([]).values()) == {0}


class TestHasCoverage:
    def test_covered(self):
        assert sat.has_coverage(sat.extract_targets(_view()))

    def test_index_has_none(self):
        assert not sat.has_coverage(sat.extract_targets(_empty_view()))

    def test_trend_alone_counts(self):
        view = {**_empty_view(), "trend": [_trend("0m", 1, 0, 0, 0, 0)]}
        assert sat.has_coverage(sat.extract_targets(view))

    def test_actions_alone_count(self):
        view = {**_empty_view(), "actions": _actions()}
        assert sat.has_coverage(sat.extract_targets(view))


class TestBuildReport:
    def test_sections(self):
        report = sat.build_report("AAA", sat.extract_targets(_view()))
        lines = report.splitlines()
        assert lines[0] == "AAA - Triple A Inc.  (TST - USD)"
        assert lines[1] == "Price 100.00 USD    20 analysts with a price target"
        assert "+50.00%" in report and "-20.00%" in report
        assert "Consensus  BUY  (mean 2.20 on 1 = strong buy ... 5 = strong sell)" in report
        assert "This month" in report and "1 month ago" in report

    def test_strong_buy_key_is_readable(self):
        view = {**_view(), "recommendation": {"key": "strong_buy", "mean": 1.4}}
        assert "Consensus  STRONG BUY" in sat.build_report("AAA", sat.extract_targets(view))

    def test_missing_consensus_and_trend(self):
        view = {**_view(), "recommendation": {"key": None, "mean": None}, "trend": []}
        report = sat.build_report("AAA", sat.extract_targets(view))
        assert "Consensus  -" in report
        assert "No rating counts from Yahoo" in report

    def test_actions_section(self):
        report = sat.build_report("AAA", sat.extract_targets(_view(actions=_actions()), 90))
        assert "Analyst actions (last 90 days)" in report
        assert "1 upgrades, 1 downgrades, 0 initiations; targets raised 1, lowered 1" in report
        lines = report.splitlines()
        alpha = next(line for line in lines if "Alpha Capital" in line)
        assert "upgrade" in alpha and "Hold -> Buy" in alpha and "130.00 -> 150.00" in alpha
        gamma = next(line for line in lines if "Gamma Research" in line)
        assert "->" not in gamma and gamma.rstrip().endswith("-")
        delta = next(line for line in lines if "Delta Partners" in line)
        assert delta.rstrip().endswith("115.00") and "->" not in delta

    def test_no_actions(self):
        report = sat.build_report("AAA", sat.extract_targets(_view(), 30))
        assert "No upgrades, downgrades or target changes from Yahoo in the last 30 days" in report


class TestParseArgs:
    def test_defaults(self):
        args = sat.parse_args(["AAPL"])
        assert (args.symbol, args.days, args.json) == ("AAPL", 90, False)

    @pytest.mark.parametrize("bad", ["0", "-5", "abc"])
    def test_bad_days_exits_2(self, bad):
        with pytest.raises(SystemExit) as exc:
            sat.parse_args(["AAPL", "--days", bad])
        assert exc.value.code == 2

    def test_missing_symbol_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            sat.parse_args([])
        assert exc.value.code == 2


class TestMain:
    def test_json_output(self, monkeypatch, capsys):
        seen = []
        monkeypatch.setattr(stock_data, "analyst_view",
                            lambda s, d: seen.append((s, d)) or _view())
        sat.main(["aaa", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert seen == [("aaa", 90)]
        assert out["symbol"] == "AAA"  # upper-cased
        assert out["upside"]["median"] == 0.1
        assert out["trend"][0]["total"] == 22
        assert "source" not in out and "notes" not in out

    def test_days_flag_is_passed_on(self, monkeypatch, capsys):
        seen = []
        monkeypatch.setattr(stock_data, "analyst_view",
                            lambda s, d: seen.append(d) or _view(actions=_actions()[:2]))
        sat.main(["AAA", "--days", "20", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert seen == [20]
        assert out["actions_days"] == 20
        assert [a["firm"] for a in out["actions"]] == ["Alpha Capital", "Beta Bank"]

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "analyst_view", lambda s, d: _view())
        sat.main(["AAA"])
        assert "Price targets" in capsys.readouterr().out

    def test_fetch_error_exits_1_json(self, monkeypatch, capsys):
        def boom(symbol, days):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(stock_data, "analyst_view", boom)
        with pytest.raises(SystemExit) as exc:
            sat.main(["ZZZ", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "failed to fetch analyst targets for 'ZZZ': Quote not found"}

    def test_no_coverage_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "analyst_view", lambda s, d: _empty_view())
        with pytest.raises(SystemExit) as exc:
            sat.main(["^GSPC"])
        assert exc.value.code == 1
        assert "no analyst coverage for '^GSPC'" in capsys.readouterr().err

    def test_unknown_flag_exits_2_before_fetch(self, monkeypatch):
        monkeypatch.setattr(stock_data, "analyst_view",
                            lambda s, d: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            sat.main(["AAA", "--bogus"])
        assert exc.value.code == 2
