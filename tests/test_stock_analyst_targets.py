"""Tests for stock_analyst_targets: target/trend/action extraction, output, main()."""

import json
import time

import pytest
import requests

import stock_analyst_targets as sat
import yahoo_finance as yf


def _trend(period, strong_buy, buy, hold, sell, strong_sell):
    return {"period": period, "strongBuy": strong_buy, "buy": buy, "hold": hold,
            "sell": sell, "strongSell": strong_sell}


DAY = 86400
NOW = 1_790_000_000  # 2026-09-21 14:13 UTC


def _grade(days_ago, firm, action, from_grade, to_grade, target_action="", target=0.0,
           prior=0.0, now=NOW):
    return {"epochGradeDate": int(now - days_ago * DAY), "firm": firm, "action": action,
            "fromGrade": from_grade, "toGrade": to_grade,
            "priceTargetAction": target_action, "currentPriceTarget": target,
            "priorPriceTarget": prior}


def _history(now=NOW):
    """``upgradeDowngradeHistory`` out of date order, one entry outside 90 days."""
    return {"history": [
        _grade(10, "Beta Bank", "down", "Buy", "Hold", "Lowers", 120.0, 140.0, now),
        _grade(2, "Alpha Capital", "up", "Hold", "Buy", "Raises", 150.0, 130.0, now),
        _grade(200, "Old Firm", "init", "", "Buy", "Announces", 90.0, 0.0, now),
        _grade(30, "Gamma Research", "reit", "Neutral", "Neutral", "", 0.0, 0.0, now),
        _grade(45, "Delta Partners", "main", "Outperform", "Outperform", "Maintains",
               115.0, 115.0, now),
    ]}


def _modules(price=100.0):
    """Minimal quoteSummary ``modules`` with every field the extractor reads."""
    return {
        "price": {"longName": "Triple A Inc.", "currency": "USD", "exchangeName": "TST",
                  "regularMarketPrice": {"raw": price}},
        "financialData": {
            "currentPrice": {"raw": price},
            "targetLowPrice": {"raw": 80.0}, "targetMedianPrice": {"raw": 110.0},
            "targetMeanPrice": {"raw": 105.0}, "targetHighPrice": {"raw": 150.0},
            "numberOfAnalystOpinions": {"raw": 20},
            "recommendationKey": "buy", "recommendationMean": {"raw": 2.2},
        },
        "recommendationTrend": {"trend": [
            # Out of order on purpose: the extractor sorts newest first.
            _trend("-1m", 5, 9, 5, 1, 0),
            _trend("0m", 6, 10, 4, 1, 1),
        ]},
    }


class TestExtractTargets:
    def test_targets_and_upside(self):
        data = sat.extract_targets(_modules())
        assert data["price"] == 100.0
        assert data["targets"] == {"low": 80.0, "median": 110.0, "mean": 105.0, "high": 150.0}
        assert data["upside"] == {"low": -0.2, "median": 0.1, "mean": 0.05, "high": 0.5}
        assert data["analysts"] == 20
        assert data["recommendation"] == {"key": "buy", "mean": 2.2}

    def test_price_falls_back_to_regular_market_price(self):
        modules = _modules()
        del modules["financialData"]["currentPrice"]
        assert sat.extract_targets(modules)["upside"]["high"] == 0.5

    def test_no_price_gives_no_upside(self):
        modules = _modules()
        del modules["financialData"]["currentPrice"]
        del modules["price"]["regularMarketPrice"]
        data = sat.extract_targets(modules)
        assert data["targets"]["high"] == 150.0
        assert set(data["upside"].values()) == {None}

    def test_recommendation_key_none_is_dropped(self):
        modules = _modules()
        modules["financialData"]["recommendationKey"] = "none"
        assert sat.extract_targets(modules)["recommendation"]["key"] is None


class TestRecommendationTrend:
    def test_sorted_newest_first_with_totals(self):
        rows = sat.recommendation_trend(_modules())
        assert [r["period"] for r in rows] == ["0m", "-1m"]
        assert rows[0] == {"period": "0m", "strong_buy": 6, "buy": 10, "hold": 4,
                           "sell": 1, "strong_sell": 1, "total": 22}

    def test_empty_rows_dropped(self):
        modules = {"recommendationTrend": {"trend": [{"period": "0m"}]}}
        assert sat.recommendation_trend(modules) == []


class TestAnalystActions:
    def test_window_and_newest_first(self):
        rows = sat.analyst_actions({"upgradeDowngradeHistory": _history()}, 90, now=NOW)
        assert [r["firm"] for r in rows] == [
            "Alpha Capital", "Beta Bank", "Gamma Research", "Delta Partners"]

    def test_fields_and_mapping(self):
        rows = sat.analyst_actions({"upgradeDowngradeHistory": _history()}, 90, now=NOW)
        assert rows[0] == {
            "date": "2026-09-19", "firm": "Alpha Capital", "action": "upgrade",
            "from_grade": "Hold", "to_grade": "Buy", "target_action": "raised",
            "target": 150.0, "prior_target": 130.0,
        }
        assert (rows[1]["action"], rows[1]["target_action"]) == ("downgrade", "lowered")
        assert (rows[3]["action"], rows[3]["target_action"]) == ("maintain", "maintained")

    def test_zero_targets_and_blank_text_become_none(self):
        rows = sat.analyst_actions({"upgradeDowngradeHistory": _history()}, 90, now=NOW)
        gamma = rows[2]
        assert gamma["action"] == "reiterate"
        assert (gamma["target_action"], gamma["target"], gamma["prior_target"]) == (None, None, None)
        old = sat.analyst_actions({"upgradeDowngradeHistory": _history()}, 365, now=NOW)[-1]
        assert (old["action"], old["from_grade"], old["prior_target"]) == ("initiate", None, None)

    def test_days_narrows_window(self):
        rows = sat.analyst_actions({"upgradeDowngradeHistory": _history()}, 7, now=NOW)
        assert [r["firm"] for r in rows] == ["Alpha Capital"]

    def test_unknown_codes_pass_through_and_undated_skipped(self):
        history = {"history": [
            _grade(1, "X", "xyz", "A", "B", "Rethinks", 1.0),
            {"firm": "No Date", "action": "up"},
        ]}
        rows = sat.analyst_actions({"upgradeDowngradeHistory": history}, 90, now=NOW)
        assert [(r["action"], r["target_action"]) for r in rows] == [("xyz", "rethinks")]

    def test_missing_module(self):
        assert sat.analyst_actions(_modules(), now=NOW) == []

    def test_summary(self):
        rows = sat.analyst_actions({"upgradeDowngradeHistory": _history()}, 365, now=NOW)
        assert sat.action_summary(rows) == {
            "upgrades": 1, "downgrades": 1, "initiations": 1,
            "targets_raised": 1, "targets_lowered": 1,
        }

    def test_extract_targets_includes_actions(self):
        modules = {**_modules(), "upgradeDowngradeHistory": _history()}
        data = sat.extract_targets(modules, 90, now=NOW)
        assert data["actions_days"] == 90
        assert len(data["actions"]) == 4
        assert data["action_summary"]["upgrades"] == 1


class TestHasCoverage:
    def test_covered(self):
        assert sat.has_coverage(sat.extract_targets(_modules()))

    def test_index_has_none(self):
        assert not sat.has_coverage(sat.extract_targets({"price": {"currency": "USD"}}))

    def test_trend_alone_counts(self):
        modules = {"recommendationTrend": _modules()["recommendationTrend"]}
        assert sat.has_coverage(sat.extract_targets(modules))

    def test_actions_alone_count(self):
        modules = {"upgradeDowngradeHistory": _history()}
        assert sat.has_coverage(sat.extract_targets(modules, 90, now=NOW))


class TestBuildReport:
    def test_sections(self):
        report = sat.build_report("AAA", sat.extract_targets(_modules()))
        lines = report.splitlines()
        assert lines[0] == "AAA - Triple A Inc.  (TST - USD)"
        assert lines[1] == "Price 100.00 USD    20 analysts with a price target"
        assert "+50.00%" in report and "-20.00%" in report
        assert "Consensus  BUY  (mean 2.20 on 1 = strong buy ... 5 = strong sell)" in report
        assert "This month" in report and "1 month ago" in report

    def test_strong_buy_key_is_readable(self):
        modules = _modules()
        modules["financialData"]["recommendationKey"] = "strong_buy"
        assert "Consensus  STRONG BUY" in sat.build_report("AAA", sat.extract_targets(modules))

    def test_missing_consensus_and_trend(self):
        modules = _modules()
        for key in ("recommendationKey", "recommendationMean"):
            del modules["financialData"][key]
        del modules["recommendationTrend"]
        report = sat.build_report("AAA", sat.extract_targets(modules))
        assert "Consensus  -" in report
        assert "No rating counts from Yahoo" in report

    def test_actions_section(self):
        modules = {**_modules(), "upgradeDowngradeHistory": _history()}
        report = sat.build_report("AAA", sat.extract_targets(modules, 90, now=NOW))
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
        report = sat.build_report("AAA", sat.extract_targets(_modules(), 30))
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
        monkeypatch.setattr(yf, "fetch_quote_summary",
                            lambda s, m: seen.append((s, m)) or _modules())
        sat.main(["aaa", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert seen == [("aaa", sat.MODULES)]
        assert out["symbol"] == "AAA"  # upper-cased
        assert out["upside"]["median"] == 0.1
        assert out["trend"][0]["total"] == 22

    def test_days_flag_limits_actions(self, monkeypatch, capsys):
        modules = {**_modules(), "upgradeDowngradeHistory": _history(now=time.time())}
        monkeypatch.setattr(yf, "fetch_quote_summary", lambda s, m: modules)
        sat.main(["AAA", "--days", "20", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert out["actions_days"] == 20
        assert [a["firm"] for a in out["actions"]] == ["Alpha Capital", "Beta Bank"]

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(yf, "fetch_quote_summary", lambda s, m: _modules())
        sat.main(["AAA"])
        assert "Price targets" in capsys.readouterr().out

    def test_fetch_error_exits_1_json(self, monkeypatch, capsys):
        def boom(symbol, modules):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(yf, "fetch_quote_summary", boom)
        with pytest.raises(SystemExit) as exc:
            sat.main(["ZZZ", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "failed to fetch analyst targets for 'ZZZ': Quote not found"}

    def test_no_coverage_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(yf, "fetch_quote_summary",
                            lambda s, m: {"price": {"currency": "USD"}})
        with pytest.raises(SystemExit) as exc:
            sat.main(["^GSPC"])
        assert exc.value.code == 1
        assert "no analyst coverage for '^GSPC'" in capsys.readouterr().err

    def test_unknown_flag_exits_2_before_fetch(self, monkeypatch):
        monkeypatch.setattr(yf, "fetch_quote_summary",
                            lambda s, m: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            sat.main(["AAA", "--bogus"])
        assert exc.value.code == 2
