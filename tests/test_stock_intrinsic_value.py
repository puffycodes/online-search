"""Tests for stock_intrinsic_value: inputs, assumptions, estimates, output, main().

The Yahoo parsing behind stock_data.fundamentals_view() (price and beta
fallbacks, the dividend from the forward yield, the quoteSummary fetch) is
tested in test_yahoo_finance.py; here every view is already in stock_data's
neutral shape.
"""

import json

import pytest
import requests

import stock_data
import stock_intrinsic_value as siv
import valuation


def _view(price=100.0, **changes):
    """A neutral fundamentals view with every input the valuation methods need."""
    view = {
        "source": "Test", "notes": [],
        "name": "Triple A Inc.", "exchange": "TST", "currency": "USD",
        "sector": "Technology", "industry": "Consumer Electronics",
        "price": price, "market_cap": 100e9, "shares_outstanding": 1e9,
        "free_cash_flow": 5e9, "operating_cash_flow": None, "ebitda": 8e9,
        "revenue": 40e9, "net_income": None, "total_debt": 2e9, "total_cash": 1e9,
        "eps_ttm": 5.0, "eps_forward": 6.0, "book_value_per_share": 20.0, "beta": 1.2,
        "trailing_pe": 20.0, "forward_pe": 16.0, "price_to_sales": 2.5, "price_to_book": None,
        "enterprise_value": 101e9, "ev_to_ebitda": 12.0,
        "gross_margin": None, "operating_margin": None, "net_margin": None,
        "return_on_equity": None, "return_on_assets": None,
        "revenue_growth": None, "earnings_growth": None,
        "debt_to_equity": None, "current_ratio": None, "quick_ratio": None,
        "dividend_per_share": 2.0, "payout_ratio": None,
        "analyst_growth_1y": 0.07, "analyst_growth_5y": 0.10,
    }
    view.update(changes)
    return view


def _args(*extra):
    return siv.parse_args(["AAA", *extra])


def _run(view, *extra):
    """collect_inputs -> resolve_assumptions -> compute_estimates for ``view``."""
    args = _args(*extra)
    inputs = siv.collect_inputs(view)
    assumptions = siv.resolve_assumptions(inputs, args)
    estimates, used = siv.compute_estimates(inputs, assumptions, args)
    return inputs, assumptions, estimates, used


class TestCollectInputs:
    def test_flattens_view(self):
        inputs = siv.collect_inputs(_view())
        assert inputs["name"] == "Triple A Inc."
        assert (inputs["exchange"], inputs["currency"]) == ("TST", "USD")
        assert (inputs["sector"], inputs["industry"]) == ("Technology", "Consumer Electronics")
        assert inputs["price"] == 100.0
        assert inputs["net_debt"] == pytest.approx(1e9)
        assert inputs["revenue_per_share"] == pytest.approx(40.0)
        assert inputs["analyst_growth_5y"] == 0.10

    def test_key_order(self):
        # build_json() prints every input, so the order is part of the output.
        assert list(siv.collect_inputs(_view())) == [
            "name", "exchange", "currency", "sector", "industry", "price", "market_cap",
            "shares", "free_cash_flow", "ebitda", "total_debt", "total_cash", "net_debt",
            "revenue", "revenue_per_share", "eps_ttm", "eps_forward", "book_value_per_share",
            "beta", "trailing_pe", "forward_pe", "price_to_sales", "enterprise_value",
            "ev_to_ebitda", "dividend_rate", "analyst_growth_5y", "analyst_growth_1y"]

    def test_shares_fall_back_to_market_cap_over_price(self):
        assert siv.collect_inputs(_view(shares_outstanding=None))["shares"] == pytest.approx(1e9)

    def test_no_shares_without_market_cap(self):
        inputs = siv.collect_inputs(_view(shares_outstanding=None, market_cap=None))
        assert (inputs["shares"], inputs["revenue_per_share"]) == (None, None)

    def test_net_debt_none_when_cash_missing(self):
        assert siv.collect_inputs(_view(total_cash=None))["net_debt"] is None

    def test_dividend_rate_is_the_dividend_per_share(self):
        assert siv.collect_inputs(_view())["dividend_rate"] == 2.0
        assert siv.collect_inputs(_view(dividend_per_share=None))["dividend_rate"] is None


class TestResolveAssumptions:
    def test_capm_and_analyst_5y_by_default(self):
        inputs = siv.collect_inputs(_view())
        a = siv.resolve_assumptions(inputs, _args())
        assert a["discount_rate"] == pytest.approx(0.04 + 1.2 * 0.05)
        assert a["notes"]["discount_rate"].startswith("CAPM")
        assert a["growth"] == 0.10
        assert a["notes"]["growth"] == "analyst 5-year EPS growth estimate"
        assert (a["terminal_growth"], a["years"]) == (0.025, 10)

    def test_user_supplied_values_win(self):
        inputs = siv.collect_inputs(_view())
        a = siv.resolve_assumptions(
            inputs, _args("--discount-rate", "0.11", "--growth", "0.03", "--years", "5")
        )
        assert (a["discount_rate"], a["growth"], a["years"]) == (0.11, 0.03, 5)
        assert a["notes"] == {"discount_rate": "user-supplied", "growth": "user-supplied"}

    def test_defaults_without_beta_or_analyst_estimates(self):
        inputs = siv.collect_inputs(_view(beta=None, analyst_growth_5y=None,
                                          analyst_growth_1y=None))
        a = siv.resolve_assumptions(inputs, _args())
        assert a["discount_rate"] == siv.DEFAULT_DISCOUNT_RATE
        assert "no beta" in a["notes"]["discount_rate"]
        assert a["growth"] == siv.DEFAULT_GROWTH
        assert "no analyst estimate" in a["notes"]["growth"]

    def test_growth_falls_back_to_analyst_1y(self):
        a = siv.resolve_assumptions(siv.collect_inputs(_view(analyst_growth_5y=None)), _args())
        assert a["growth"] == 0.07
        assert a["notes"]["growth"] == "analyst 1-year EPS growth estimate"

    def test_discount_rate_raised_above_terminal_growth(self):
        inputs = siv.collect_inputs(_view())
        a = siv.resolve_assumptions(
            inputs, _args("--discount-rate", "0.03", "--terminal-growth", "0.04")
        )
        assert a["discount_rate"] == pytest.approx(0.06)
        assert "raised to 6.00%" in a["notes"]["discount_rate"]


class TestComputeEstimates:
    def test_every_method_runs_with_full_inputs(self):
        inputs, a, est, used = _run(_view())
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
        _, _, est, used = _run(_view(), "--pe", "15", "--ev-ebitda", "10", "--ps", "2")
        assert est["pe_multiple"] == pytest.approx(75.0)
        assert est["ev_ebitda_multiple"] == pytest.approx((8e9 * 10 - 1e9) / 1e9)
        assert est["ps_multiple"] == pytest.approx(80.0)
        assert (used["pe_source"], used["ev_ebitda_source"], used["ps_source"]) == (
            "user-supplied", "user-supplied", "user-supplied")

    def test_negative_fcf_blanks_dcf_and_reverse_dcf(self):
        _, _, est, _ = _run(_view(free_cash_flow=-1e9))
        assert est["dcf_two_stage"] is None
        assert est["reverse_dcf_implied_growth"] is None
        assert est["pe_multiple"] is not None  # other methods unaffected

    def test_non_payer_has_no_dividend_estimate(self):
        assert _run(_view(dividend_per_share=None))[2]["dividend_discount"] is None

    def test_loss_maker_has_no_earnings_estimates(self):
        _, _, est, used = _run(_view(eps_ttm=-2.0))
        assert est["pe_multiple"] is None and est["graham"] is None
        assert used["graham_pe"] is None

    def test_graham_multiple_capped(self):
        _, _, est, used = _run(_view(), "--growth", "0.30")  # 8.5 + 60 > cap
        assert used["graham_pe"] == siv.GRAHAM_PE_CAP
        assert est["graham"] == pytest.approx(5.0 * siv.GRAHAM_PE_CAP)

    def test_graham_skipped_for_steep_negative_growth(self):
        _, _, est, used = _run(_view(), "--growth", "-0.05")  # 8.5 - 10 < 0
        assert est["graham"] is None and used["graham_pe"] is None

    def test_missing_net_debt_treated_as_zero(self):
        _, _, est, _ = _run(_view(total_debt=None))
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
        inputs, a, est, used = _run(_view())
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
        inputs, a, est, used = _run(_view())
        report = siv.build_report("AAA", inputs, a, est, used)
        assert report.splitlines()[0] == "AAA - Triple A Inc.  (TST - USD)"
        for heading in ("Fundamentals", "Assumptions", "Intrinsic value estimates"):
            assert heading in report
        assert "P/E multiple (20.00x)" in report
        assert "Reverse DCF -> implied growth" in report
        assert "dividend yield < 1%" not in report  # 2.0 / 100 = 2%

    def test_build_report_flags_low_dividend_yield(self):
        report = siv.build_report("AAA", *_run(_view(dividend_per_share=0.5)))  # 0.5% yield
        assert "dividend yield < 1%" in report


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
        seen = []
        monkeypatch.setattr(stock_data, "fundamentals_view", lambda s: seen.append(s) or _view())
        siv.main(["aaa", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert seen == ["aaa"]
        assert out["symbol"] == "AAA"  # upper-cased
        assert out["estimates"]["pe_multiple"]["value_per_share"] == pytest.approx(100.0)
        assert "source" not in out and "notes" not in out["inputs"]

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "fundamentals_view", lambda s: _view())
        siv.main(["AAA"])
        assert "Intrinsic value estimates" in capsys.readouterr().out

    def test_fetch_error_exits_1_json(self, monkeypatch, capsys):
        def boom(symbol):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(stock_data, "fundamentals_view", boom)
        with pytest.raises(SystemExit) as exc:
            siv.main(["ZZZ", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "failed to fetch fundamentals for 'ZZZ': Quote not found"}

    def test_no_price_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "fundamentals_view", lambda s: _view(price=None))
        with pytest.raises(SystemExit) as exc:
            siv.main(["AAA"])
        assert exc.value.code == 1
        assert "no usable fundamentals" in capsys.readouterr().err

    def test_invalid_years_exits_2_before_fetch(self, monkeypatch):
        monkeypatch.setattr(stock_data, "fundamentals_view",
                            lambda s: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            siv.main(["AAA", "--years", "0"])
        assert exc.value.code == 2
