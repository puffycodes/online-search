"""Tests for valuation: growth-path handling, the estimators, and the reverse-DCF solver."""

import pytest

from valuation import (
    _growth_path,
    discounted_cash_flow,
    equity_from_enterprise,
    ev_multiple_value,
    gordon_growth_value,
    implied_growth_rate,
    multiple_value,
)


class TestGrowthPath:
    def test_scalar_repeated(self):
        assert _growth_path(0.05, 3) == [0.05, 0.05, 0.05]

    def test_iterable_used_as_is_years_ignored(self):
        assert _growth_path([0.08, 0.06, 0.04], years=99) == [0.08, 0.06, 0.04]

    def test_empty_iterable_raises(self):
        with pytest.raises(ValueError, match="at least one forecast year"):
            _growth_path([], 5)

    def test_scalar_without_years_raises(self):
        with pytest.raises(ValueError, match="years is required"):
            _growth_path(0.05, None)

    @pytest.mark.parametrize("years", [0, -3])
    def test_scalar_non_positive_years_raises(self, years):
        with pytest.raises(ValueError, match="positive integer"):
            _growth_path(0.05, years)


class TestGordonGrowthValue:
    def test_reference_value(self):
        assert gordon_growth_value(5.0, 0.08, 0.03) == pytest.approx(100.0)

    @pytest.mark.parametrize("rate,growth", [(0.03, 0.05), (0.05, 0.05)])
    def test_rate_not_above_growth_raises(self, rate, growth):
        with pytest.raises(ValueError, match="must exceed growth"):
            gordon_growth_value(5.0, rate, growth)


class TestEquityFromEnterprise:
    def test_net_cash_is_added_back(self):
        got = equity_from_enterprise(1_680_000, net_debt=-50_000, shares=15_000)
        assert got == pytest.approx(115.3333, abs=1e-3)

    def test_total_equity_without_shares(self):
        assert equity_from_enterprise(1000, net_debt=200) == 800

    @pytest.mark.parametrize("shares", [0, -5])
    def test_non_positive_shares_raises(self, shares):
        with pytest.raises(ValueError, match="shares must be positive"):
            equity_from_enterprise(1000, net_debt=0, shares=shares)


class TestDiscountedCashFlow:
    def test_reference_scalar(self):
        assert discounted_cash_flow(100, 0.09, 0.05, 5) == pytest.approx(1656.27, abs=0.01)

    def test_reference_per_year_list(self):
        got = discounted_cash_flow(100, 0.09, [0.08, 0.06, 0.04], shares=100)
        assert got == pytest.approx(16.2701, abs=1e-4)

    def test_scalar_and_equivalent_list_match(self):
        a = discounted_cash_flow(100, 0.09, 0.05, 3)
        b = discounted_cash_flow(100, 0.09, [0.05, 0.05, 0.05])
        assert a == pytest.approx(b)

    def test_terminal_growth_above_discount_raises(self):
        with pytest.raises(ValueError):
            discounted_cash_flow(100, 0.03, 0.02, 5, terminal_growth=0.05)

    def test_net_debt_and_shares_bridge_to_equity_per_share(self):
        enterprise_equity = discounted_cash_flow(100, 0.09, 0.05, 5)
        got = discounted_cash_flow(100, 0.09, 0.05, 5, net_debt=200, shares=10)
        assert got == pytest.approx((enterprise_equity - 200) / 10)


class TestMultipleValue:
    def test_multiple_value(self):
        assert multiple_value(6.5, 28) == 182.0

    def test_ev_multiple_value(self):
        got = ev_multiple_value(120_000, 14, net_debt=200_000, shares=15_000)
        assert got == pytest.approx(98.6667, abs=1e-4)


class TestImpliedGrowthRate:
    def test_round_trips_with_dcf(self):
        value = discounted_cash_flow(100, 0.09, 0.05, 5)
        assert implied_growth_rate(value, 100, 0.09, 5) == pytest.approx(0.05, abs=1e-4)

    def test_reference_value(self):
        assert implied_growth_rate(1656.27, 100, 0.09, 5) == pytest.approx(0.05, abs=1e-4)

    def test_monotonic_in_price(self):
        lo = implied_growth_rate(1000, 100, 0.09, 5)
        hi = implied_growth_rate(3000, 100, 0.09, 5)
        assert hi > lo

    def test_price_too_high_raises(self):
        with pytest.raises(ValueError, match="implausibly high"):
            implied_growth_rate(1e15, 100, 0.09, 5)

    def test_price_too_low_raises(self):
        with pytest.raises(ValueError, match="implausibly low"):
            implied_growth_rate(-500, 100, 0.09, 5)

    @pytest.mark.parametrize("years", [None, 0, -3])
    def test_bad_years_raises(self, years):
        with pytest.raises(ValueError, match="positive integer"):
            implied_growth_rate(1000, 100, 0.09, years)
