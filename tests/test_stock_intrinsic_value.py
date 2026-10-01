"""Tests for stock_intrinsic_value: fetch/crumb handshake, parsing, assumptions, estimates, output, main()."""

import json

import pytest
import requests

import stock_intrinsic_value as siv
import valuation
from helpers import FakeResponse, FakeSession


def _modules(price=100.0):
    """Minimal quoteSummary ``modules`` with every input the valuation methods need."""
    return {
        "price": {"longName": "Triple A Inc.", "currency": "USD", "exchangeName": "TST",
                  "regularMarketPrice": {"raw": price}, "marketCap": {"raw": 100e9}},
        "financialData": {"currentPrice": {"raw": price}, "freeCashflow": {"raw": 5e9},
                          "ebitda": {"raw": 8e9}, "totalDebt": {"raw": 2e9},
                          "totalCash": {"raw": 1e9}, "totalRevenue": {"raw": 40e9}},
        "defaultKeyStatistics": {"sharesOutstanding": {"raw": 1e9}, "trailingEps": {"raw": 5.0},
                                 "forwardEps": {"raw": 6.0}, "bookValue": {"raw": 20.0},
                                 "beta": {"raw": 1.2}, "enterpriseValue": {"raw": 101e9},
                                 "enterpriseToEbitda": {"raw": 12.0}},
        "summaryDetail": {"trailingPE": {"raw": 20.0}, "forwardPE": {"raw": 16.0},
                          "priceToSalesTrailing12Months": {"raw": 2.5},
                          "dividendRate": {"raw": 2.0}},
        "summaryProfile": {"sector": "Technology", "industry": "Consumer Electronics"},
        "earningsTrend": {"trend": [{"period": "+1y", "growth": {"raw": 0.07}},
                                    {"period": "+5y", "growth": {"raw": 0.10}}]},
    }


def _args(*extra):
    return siv.parse_args(["AAA", *extra])


def _run(modules, *extra):
    """collect_inputs -> resolve_assumptions -> compute_estimates for ``modules``."""
    args = _args(*extra)
    inputs = siv.collect_inputs(modules)
    assumptions = siv.resolve_assumptions(inputs, args)
    estimates, used = siv.compute_estimates(inputs, assumptions, args)
    return inputs, assumptions, estimates, used


class TestParseHelpers:
    @pytest.mark.parametrize("node,expected", [
        ({"a": {"b": {"raw": 3}}}, 3.0),
        ({"a": {"b": 4.5}}, 4.5),
        ({"a": {"b": True}}, None),      # bools are not numbers here
        ({"a": {"b": "7"}}, None),       # strings are not numbers here
        ({"a": {"b": {"fmt": "1M"}}}, None),
        ({"a": None}, None),
        ({}, None),
    ])
    def test_num(self, node, expected):
        assert siv._num(node, "a", "b") == expected

    @pytest.mark.parametrize("node,expected", [
        ({"a": {"b": "Tech"}}, "Tech"),
        ({"a": {"b": ""}}, None),
        ({"a": {"b": 3}}, None),
        ({"a": "flat"}, None),
    ])
    def test_text(self, node, expected):
        assert siv._text(node, "a", "b") == expected

    def test_analyst_growth_by_period(self):
        modules = _modules()
        assert siv._analyst_growth(modules, "+5y") == 0.10
        assert siv._analyst_growth(modules, "+1y") == 0.07
        assert siv._analyst_growth(modules, "+2y") is None
        assert siv._analyst_growth({}, "+5y") is None


class TestCollectInputs:
    def test_flattens_modules(self):
        inputs = siv.collect_inputs(_modules())
        assert inputs["name"] == "Triple A Inc."
        assert (inputs["exchange"], inputs["currency"]) == ("TST", "USD")
        assert (inputs["sector"], inputs["industry"]) == ("Technology", "Consumer Electronics")
        assert inputs["price"] == 100.0
        assert inputs["net_debt"] == pytest.approx(1e9)
        assert inputs["revenue_per_share"] == pytest.approx(40.0)
        assert inputs["analyst_growth_5y"] == 0.10

    def test_price_falls_back_to_regular_market_price(self):
        modules = _modules()
        del modules["financialData"]["currentPrice"]
        modules["price"]["regularMarketPrice"] = {"raw": 90.0}
        assert siv.collect_inputs(modules)["price"] == 90.0

    def test_shares_fall_back_to_market_cap_over_price(self):
        modules = _modules()
        del modules["defaultKeyStatistics"]["sharesOutstanding"]
        assert siv.collect_inputs(modules)["shares"] == pytest.approx(1e9)

    def test_net_debt_none_when_cash_missing(self):
        modules = _modules()
        del modules["financialData"]["totalCash"]
        assert siv.collect_inputs(modules)["net_debt"] is None

    def test_beta_falls_back_to_summary_detail(self):
        modules = _modules()
        del modules["defaultKeyStatistics"]["beta"]
        modules["summaryDetail"]["beta"] = {"raw": 0.8}
        assert siv.collect_inputs(modules)["beta"] == 0.8

    def test_name_falls_back_to_short_name(self):
        modules = _modules()
        modules["price"]["longName"] = None
        modules["price"]["shortName"] = "AAA Co"
        assert siv.collect_inputs(modules)["name"] == "AAA Co"


class TestResolveAssumptions:
    def test_capm_and_analyst_5y_by_default(self):
        inputs = siv.collect_inputs(_modules())
        a = siv.resolve_assumptions(inputs, _args())
        assert a["discount_rate"] == pytest.approx(0.04 + 1.2 * 0.05)
        assert a["notes"]["discount_rate"].startswith("CAPM")
        assert a["growth"] == 0.10
        assert a["notes"]["growth"] == "analyst 5-year EPS growth estimate"
        assert (a["terminal_growth"], a["years"]) == (0.025, 10)

    def test_user_supplied_values_win(self):
        inputs = siv.collect_inputs(_modules())
        a = siv.resolve_assumptions(
            inputs, _args("--discount-rate", "0.11", "--growth", "0.03", "--years", "5")
        )
        assert (a["discount_rate"], a["growth"], a["years"]) == (0.11, 0.03, 5)
        assert a["notes"] == {"discount_rate": "user-supplied", "growth": "user-supplied"}

    def test_defaults_without_beta_or_analyst_estimates(self):
        inputs = siv.collect_inputs(_modules())
        inputs.update(beta=None, analyst_growth_5y=None, analyst_growth_1y=None)
        a = siv.resolve_assumptions(inputs, _args())
        assert a["discount_rate"] == siv.DEFAULT_DISCOUNT_RATE
        assert "no beta" in a["notes"]["discount_rate"]
        assert a["growth"] == siv.DEFAULT_GROWTH
        assert "no analyst estimate" in a["notes"]["growth"]

    def test_growth_falls_back_to_analyst_1y(self):
        inputs = siv.collect_inputs(_modules())
        inputs["analyst_growth_5y"] = None
        a = siv.resolve_assumptions(inputs, _args())
        assert a["growth"] == 0.07
        assert a["notes"]["growth"] == "analyst 1-year EPS growth estimate"

    def test_discount_rate_raised_above_terminal_growth(self):
        inputs = siv.collect_inputs(_modules())
        a = siv.resolve_assumptions(
            inputs, _args("--discount-rate", "0.03", "--terminal-growth", "0.04")
        )
        assert a["discount_rate"] == pytest.approx(0.06)
        assert "raised to 6.00%" in a["notes"]["discount_rate"]


class TestComputeEstimates:
    def test_every_method_runs_with_full_inputs(self):
        inputs, a, est, used = _run(_modules())
        assert all(v is not None for v in est.values())
        assert est["dcf_two_stage"] == pytest.approx(valuation.discounted_cash_flow(
            5e9, a["discount_rate"], a["growth"], 10,
            terminal_growth=0.025, net_debt=1e9, shares=1e9,
        ))
        # The reverse DCF at that price should round-trip to a growth that values it there.
        implied = est["reverse_dcf_implied_growth"]
        assert valuation.discounted_cash_flow(
            5e9, a["discount_rate"], implied, 10, terminal_growth=0.025, net_debt=1e9, shares=1e9,
        ) == pytest.approx(100.0, rel=1e-6)
        assert est["dividend_discount"] == pytest.approx(
            2.0 * 1.025 / (a["discount_rate"] - 0.025)
        )
        assert est["pe_multiple"] == pytest.approx(100.0)          # 5 EPS x current 20 P/E
        assert est["graham"] == pytest.approx(5.0 * (8.5 + 2 * 10.0))
        assert est["ev_ebitda_multiple"] == pytest.approx((8e9 * 12 - 1e9) / 1e9)
        assert est["ps_multiple"] == pytest.approx(40.0 * 2.5)
        assert est["ev_reported_to_equity"] == pytest.approx(100.0)
        assert used["pe_source"] == "current trailing P/E"

    def test_user_multiples_override_current_ones(self):
        _, _, est, used = _run(_modules(), "--pe", "15", "--ev-ebitda", "10", "--ps", "2")
        assert est["pe_multiple"] == pytest.approx(75.0)
        assert est["ev_ebitda_multiple"] == pytest.approx((8e9 * 10 - 1e9) / 1e9)
        assert est["ps_multiple"] == pytest.approx(80.0)
        assert (used["pe_source"], used["ev_ebitda_source"], used["ps_source"]) == (
            "user-supplied", "user-supplied", "user-supplied")

    def test_negative_fcf_blanks_dcf_and_reverse_dcf(self):
        modules = _modules()
        modules["financialData"]["freeCashflow"] = {"raw": -1e9}
        _, _, est, _ = _run(modules)
        assert est["dcf_two_stage"] is None
        assert est["reverse_dcf_implied_growth"] is None
        assert est["pe_multiple"] is not None  # other methods unaffected

    def test_non_payer_has_no_dividend_estimate(self):
        modules = _modules()
        del modules["summaryDetail"]["dividendRate"]
        assert _run(modules)[2]["dividend_discount"] is None

    def test_loss_maker_has_no_earnings_estimates(self):
        modules = _modules()
        modules["defaultKeyStatistics"]["trailingEps"] = {"raw": -2.0}
        _, _, est, used = _run(modules)
        assert est["pe_multiple"] is None and est["graham"] is None
        assert used["graham_pe"] is None

    def test_graham_multiple_capped(self):
        _, _, est, used = _run(_modules(), "--growth", "0.30")  # 8.5 + 60 > cap
        assert used["graham_pe"] == siv.GRAHAM_PE_CAP
        assert est["graham"] == pytest.approx(5.0 * siv.GRAHAM_PE_CAP)

    def test_graham_skipped_for_steep_negative_growth(self):
        _, _, est, used = _run(_modules(), "--growth", "-0.05")  # 8.5 - 10 < 0
        assert est["graham"] is None and used["graham_pe"] is None

    def test_missing_net_debt_treated_as_zero(self):
        modules = _modules()
        del modules["financialData"]["totalDebt"]
        _, _, est, _ = _run(modules)
        assert est["ev_reported_to_equity"] == pytest.approx(101.0)


class TestVsPrice:
    @pytest.mark.parametrize("price,value,expected", [
        (110.0, 100.0, 0.10),
        (90.0, 100.0, -0.10),
        (100.0, None, None),
        (100.0, 0.0, None),
        (100.0, -5.0, None),
        (None, 100.0, None),
    ])
    def test_gap(self, price, value, expected):
        result = siv._vs_price(price, value)
        assert result == (pytest.approx(expected) if expected is not None else None)


class TestOutput:
    def test_build_json_shape(self):
        inputs, a, est, used = _run(_modules())
        out = siv.build_json("AAA", inputs, a, est, used)
        assert set(out) == {"symbol", "name", "exchange", "currency", "sector", "industry",
                            "price", "inputs", "assumptions", "multiples_used", "estimates"}
        assert not {"name", "exchange", "currency", "sector", "industry", "price"} & set(out["inputs"])
        assert out["estimates"]["pe_multiple"] == {"value_per_share": pytest.approx(100.0),
                                                   "price_vs_estimate": pytest.approx(0.0)}
        assert set(out["estimates"]["reverse_dcf_implied_growth"]) == {
            "implied_growth", "analyst_growth_5y"}
        json.dumps(out)

    def test_build_report_sections(self):
        inputs, a, est, used = _run(_modules())
        report = siv.build_report("AAA", inputs, a, est, used)
        assert report.splitlines()[0] == "AAA - Triple A Inc.  (TST - USD)"
        for heading in ("Fundamentals", "Assumptions", "Intrinsic value estimates"):
            assert heading in report
        assert "P/E multiple (20.00x)" in report
        assert "Reverse DCF -> implied growth" in report
        assert "dividend yield < 1%" not in report  # 2.0 / 100 = 2%

    def test_build_report_flags_low_dividend_yield(self):
        modules = _modules()
        modules["summaryDetail"]["dividendRate"] = {"raw": 0.5}  # 0.5% yield
        report = siv.build_report("AAA", *_run(modules))
        assert "dividend yield < 1%" in report


class TestFetchFundamentals:
    def _patch_session(self, monkeypatch, session):
        monkeypatch.setattr(siv.requests, "Session", lambda: session)

    def test_cookie_crumb_then_quote_summary(self, monkeypatch):
        session = FakeSession(get_responses=[
            FakeResponse(text="cookie"),
            FakeResponse(text="crumb123"),
            FakeResponse(json_data={"quoteSummary": {"result": [_modules()], "error": None}}),
        ])
        self._patch_session(monkeypatch, session)
        assert siv.fetch_fundamentals("AAA") == _modules()
        urls = [call[0] for call in session.get_calls]
        assert urls[:2] == [siv.yf.COOKIE_URLS[0], siv.yf.CRUMB_URL]
        assert urls[2] == siv.QUOTE_SUMMARY_HOSTS[0].format(symbol="AAA")
        params = session.get_calls[2][1]["params"]
        assert params["crumb"] == "crumb123"
        assert params["modules"] == ",".join(siv.MODULES)
        assert session.headers == siv.yf.HEADERS

    def test_error_on_first_host_falls_through_to_next(self, monkeypatch):
        session = FakeSession(get_responses=[
            FakeResponse(text="cookie"),
            FakeResponse(text="crumb123"),
            FakeResponse(json_data={"quoteSummary": {"error": {"description": "busy"}}}),
            FakeResponse(json_data={"quoteSummary": {"result": [{"ok": 1}]}}),
        ])
        self._patch_session(monkeypatch, session)
        assert siv.fetch_fundamentals("AAA") == {"ok": 1}
        assert session.get_calls[3][0] == siv.QUOTE_SUMMARY_HOSTS[1].format(symbol="AAA")

    def test_html_crumb_is_ignored_and_crumbless_attempts_used(self, monkeypatch):
        session = FakeSession(get_responses=[
            FakeResponse(text="cookie"),
            FakeResponse(text="<html>consent</html>"),
            FakeResponse(json_data={"quoteSummary": {"result": [{"ok": 1}]}}),
        ])
        self._patch_session(monkeypatch, session)
        assert siv.fetch_fundamentals("AAA") == {"ok": 1}
        assert "crumb" not in session.get_calls[2][1]["params"]

    def test_all_attempts_fail_raises_last_error(self, monkeypatch):
        not_found = {"quoteSummary": {"error": {"description": "Quote not found for symbol: ZZZ"}}}
        session = FakeSession(get_responses=[FakeResponse(text="cookie"), FakeResponse(text="crumb123")]
                              + [FakeResponse(json_data=not_found) for _ in range(4)])
        self._patch_session(monkeypatch, session)
        with pytest.raises(requests.RequestException, match="Quote not found"):
            siv.fetch_fundamentals("ZZZ")
        assert len(session.get_calls) == 6  # cookie, crumb, 2 hosts x (with, without crumb)

    def test_non_json_response_reports_status(self, monkeypatch):
        session = FakeSession(get_responses=[FakeResponse(text="cookie"), FakeResponse(text="")]
                              + [FakeResponse(json_data=None, status_code=429) for _ in range(2)])
        self._patch_session(monkeypatch, session)
        with pytest.raises(requests.RequestException, match=r"non-JSON response \(HTTP 429\)"):
            siv.fetch_fundamentals("AAA")


class TestParseArgs:
    def test_defaults(self):
        args = _args()
        assert args.symbol == "AAA"
        assert (args.discount_rate, args.growth, args.pe, args.ev_ebitda, args.ps) == (
            None, None, None, None, None)
        assert (args.terminal_growth, args.years) == (0.025, 10)
        assert (args.risk_free, args.equity_risk_premium) == (0.04, 0.05)
        assert args.json is False

    @pytest.mark.parametrize("argv", [
        ["--years", "0"], ["--years", "x"], ["--discount-rate", "abc"], ["--pe", "high"],
    ])
    def test_invalid_values_exit_2(self, argv):
        with pytest.raises(SystemExit) as exc:
            _args(*argv)
        assert exc.value.code == 2


class TestMain:
    def test_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(siv, "fetch_fundamentals", lambda s: _modules())
        siv.main(["aaa", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert out["symbol"] == "AAA"  # upper-cased
        assert out["estimates"]["pe_multiple"]["value_per_share"] == pytest.approx(100.0)

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(siv, "fetch_fundamentals", lambda s: _modules())
        siv.main(["AAA"])
        assert "Intrinsic value estimates" in capsys.readouterr().out

    def test_fetch_error_exits_1_json(self, monkeypatch, capsys):
        def boom(symbol):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(siv, "fetch_fundamentals", boom)
        with pytest.raises(SystemExit) as exc:
            siv.main(["ZZZ", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "failed to fetch fundamentals for 'ZZZ': Quote not found"}

    def test_no_price_exits_1(self, monkeypatch, capsys):
        modules = _modules()
        del modules["financialData"]["currentPrice"]
        del modules["price"]["regularMarketPrice"]
        monkeypatch.setattr(siv, "fetch_fundamentals", lambda s: modules)
        with pytest.raises(SystemExit) as exc:
            siv.main(["AAA"])
        assert exc.value.code == 1
        assert "no usable fundamentals" in capsys.readouterr().err

    def test_invalid_years_exits_2_before_fetch(self, monkeypatch):
        monkeypatch.setattr(siv, "fetch_fundamentals", lambda s: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            siv.main(["AAA", "--years", "0"])
        assert exc.value.code == 2
