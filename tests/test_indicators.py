"""Tests for indicators: the price-series transforms, trend classifier, _ols_slope, and risk metrics."""

import pytest

import math

from indicators import (
    _ols_slope,
    correlation,
    max_drawdown,
    moving_average,
    moving_average_cross,
    moving_average_cross_flip,
    price_vs_moving_average,
    rebase,
    returns,
    trend,
    volatility,
)


class TestMovingAverage:
    def test_basic_window(self):
        assert moving_average([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]

    def test_window_one_is_identity(self):
        assert moving_average([1, 2, 3], 1) == [1.0, 2.0, 3.0]

    def test_window_longer_than_series_all_none(self):
        assert moving_average([1, 2, 3], 5) == [None, None, None]

    def test_accepts_any_iterable(self):
        assert moving_average(iter([2, 4, 6]), 2) == [None, 3.0, 5.0]

    @pytest.mark.parametrize("bad", [0, -1])
    def test_non_positive_window_raises(self, bad):
        with pytest.raises(ValueError, match="positive integer"):
            moving_average([1, 2, 3], bad)


class TestPriceVsMovingAverage:
    def test_reference_example(self):
        assert price_vs_moving_average([10, 10, 10, 7, 13], 3) == [
            None, None, "equal", "below", "above",
        ]


class TestMovingAverageCross:
    def test_golden_cross(self):
        assert moving_average_cross([1, 2, 3, 4, 5, 6], 2, 4) == [
            None, None, None, "above", "above", "above",
        ]

    def test_death_cross(self):
        assert moving_average_cross([6, 5, 4, 3, 2, 1], 2, 4) == [
            None, None, None, "below", "below", "below",
        ]

    def test_none_prefix_len_is_max_window_minus_one(self):
        out = moving_average_cross([5, 1, 4, 2, 3, 6, 7, 8], 2, 5)
        assert out[:4] == [None, None, None, None]
        assert out[4] is not None

    def test_equal_when_averages_tie(self):
        assert moving_average_cross([2, 2, 2, 2], 1, 2) == [
            None, "equal", "equal", "equal",
        ]


class TestMovingAverageCrossFlip:
    def test_up_flip(self):
        assert moving_average_cross_flip([3, 1, 1, 2, 3], 1, 2) == [
            None, False, False, True, False,
        ]

    def test_down_flip(self):
        assert moving_average_cross_flip([1, 2, 3, 2, 1], 1, 2) == [
            None, False, False, True, False,
        ]

    def test_no_flip_in_steady_uptrend(self):
        assert moving_average_cross_flip([1, 2, 3, 4, 5, 6], 2, 4) == [
            None, None, None, False, False, False,
        ]

    def test_double_flip_fires_twice(self):
        # below -> above -> below across a spike
        out = moving_average_cross_flip([10, 1, 1, 20, 20, 1, 1], 1, 2)
        assert out.count(True) == 2

    def test_equal_run_between_sides_is_stepped_over(self):
        # above -> equal, equal -> below: the flip still reports where the
        # new side (below) first shows, not on the equal sessions themselves.
        prices = [1, 3, 2, 2, 2, 1, 3]
        assert moving_average_cross_flip(prices, 1, 2) == [
            None, False, True, False, False, False, True,
        ]


class TestRebase:
    def test_default_base_first(self):
        assert rebase([50, 100, 150]) == [100.0, 200.0, 300.0]

    def test_explicit_base_index(self):
        assert rebase([50, 100, 150], n=1) == [50.0, 100.0, 150.0]

    def test_base_index_end(self):
        out = rebase([50, 100, 150], n=2)
        assert out[2] == 100.0
        assert out[0] == pytest.approx(33.3333, abs=1e-3)

    def test_zero_base_raises(self):
        with pytest.raises(ValueError, match="non-zero"):
            rebase([0, 1, 2])

    def test_out_of_range_index_raises(self):
        # Known inconsistency: unlike the zero-base case above, an
        # out-of-range n falls straight through to list indexing and raises
        # IndexError, not the module's usual ValueError.
        with pytest.raises(IndexError):
            rebase([50, 100, 150], n=5)


class TestOlsSlope:
    @pytest.mark.parametrize("values,slope", [
        ([0, 1, 2, 3], 1.0),
        ([5, 5, 5], 0.0),
        ([0, 2, 4], 2.0),
        ([3, 2, 1], -1.0),
    ])
    def test_slope(self, values, slope):
        assert _ols_slope(values) == pytest.approx(slope)


class TestTrend:
    def test_up(self):
        assert trend([1, 2, 3, 4, 5]) == "up"

    def test_down(self):
        assert trend([5, 4, 3, 2, 1]) == "down"

    def test_flat(self):
        assert trend([10, 10, 10, 10]) == "flat"

    def test_window_limits_to_recent(self):
        assert trend([100, 100, 100, 1, 2, 3], window=3) == "up"

    def test_window_below_two_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            trend([1, 2, 3], window=1)

    def test_too_few_prices_raises(self):
        with pytest.raises(ValueError, match="at least 2 prices"):
            trend([5])

    def test_zero_mean_is_flat(self):
        assert trend([0, 0, 0]) == "flat"

    def test_flat_threshold_controls_sensitivity(self):
        prices = [100, 100.5, 101]
        assert trend(prices, flat_threshold=0.05) == "flat"
        assert trend(prices, flat_threshold=0.0001) == "up"

    def test_negative_prices_sign_follows_slope_not_mean(self):
        # A genuinely rising all-negative series (-5 up to -1) must read
        # "up": the fractional-move scale uses abs(mean), so a negative mean
        # doesn't flip the sign of the slope-derived direction.
        assert trend([-5, -4, -3, -2, -1]) == "up"
        assert trend([-1, -2, -3, -4, -5]) == "down"


class TestReturns:
    def test_basic(self):
        assert returns([100, 150, 75]) == [None, 0.5, -0.5]

    def test_same_length_as_input(self):
        assert len(returns([1, 2, 3, 4])) == 4

    def test_single_price(self):
        assert returns([5]) == [None]

    def test_empty(self):
        assert returns([]) == []

    def test_accepts_any_iterable(self):
        assert returns(iter([2, 4])) == [None, 1.0]

    def test_zero_before_last_raises(self):
        with pytest.raises(ValueError, match="non-zero"):
            returns([10, 0, 5])

    def test_zero_last_price_is_minus_one(self):
        # Only a zero *divisor* is a problem; a final 0 is a -100% session.
        assert returns([10, 0]) == [None, -1.0]


class TestVolatility:
    def test_per_session(self):
        # returns 0.5, -0.5: mean 0, sample variance 0.5
        assert volatility([100, 150, 75], periods_per_year=1) == pytest.approx(
            math.sqrt(0.5))

    def test_annualized_by_sqrt_periods(self):
        prices = [100, 102, 99, 103, 101]
        assert volatility(prices) == pytest.approx(
            volatility(prices, periods_per_year=1) * math.sqrt(252))

    def test_constant_series_is_zero(self):
        assert volatility([10, 10, 10]) == 0.0

    def test_steady_growth_is_zero(self):
        # Same return every session: no swing around the mean.
        assert volatility([100, 110, 121, 133.1]) == pytest.approx(0.0, abs=1e-12)

    def test_up_and_down_moves_count_alike(self):
        assert volatility([100, 150, 75]) == pytest.approx(
            volatility([100, 50, 75]))

    def test_too_few_prices_raises(self):
        with pytest.raises(ValueError, match="at least 3 prices"):
            volatility([100, 101])

    @pytest.mark.parametrize("bad", [0, -252])
    def test_non_positive_periods_raises(self, bad):
        with pytest.raises(ValueError, match="periods_per_year"):
            volatility([1, 2, 3], periods_per_year=bad)

    def test_zero_price_raises(self):
        with pytest.raises(ValueError, match="non-zero"):
            volatility([10, 0, 5])


class TestMaxDrawdown:
    def test_reference_example(self):
        assert max_drawdown([100, 120, 90, 110]) == {
            "drawdown": -0.25, "peak": 1, "trough": 2, "recovery": None,
        }

    def test_recovery_index(self):
        assert max_drawdown([100, 50, 80, 100, 90]) == {
            "drawdown": -0.5, "peak": 0, "trough": 1, "recovery": 3,
        }

    def test_recovery_above_peak(self):
        assert max_drawdown([100, 50, 120])["recovery"] == 2

    def test_rising_series_has_no_drawdown(self):
        assert max_drawdown([1, 2, 3]) == {
            "drawdown": 0.0, "peak": None, "trough": None, "recovery": None,
        }

    def test_single_price(self):
        assert max_drawdown([5])["drawdown"] == 0.0

    def test_picks_largest_not_latest(self):
        # A -50% fall early beats a later -20% one from a higher peak.
        out = max_drawdown([100, 50, 200, 160])
        assert (out["drawdown"], out["peak"], out["trough"]) == (-0.5, 0, 1)

    def test_later_larger_fall_from_new_peak(self):
        out = max_drawdown([100, 90, 200, 100])
        assert (out["drawdown"], out["peak"], out["trough"]) == (-0.5, 2, 3)

    def test_tie_keeps_earliest(self):
        out = max_drawdown([100, 50, 100, 50])
        assert (out["peak"], out["trough"], out["recovery"]) == (0, 1, 2)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="at least 1 price"):
            max_drawdown([])

    @pytest.mark.parametrize("bad", [[10, 0, 5], [10, -1]])
    def test_non_positive_price_raises(self, bad):
        with pytest.raises(ValueError, match="positive"):
            max_drawdown(bad)


class TestCorrelation:
    def test_perfect_positive(self):
        assert correlation([100, 150, 75], [10, 15, 7.5]) == pytest.approx(1.0)

    def test_perfect_negative(self):
        assert correlation([100, 150, 75], [100, 50, 75]) == pytest.approx(-1.0)

    def test_uses_returns_not_prices(self):
        # Both prices rise every session, but the size of each rise is
        # opposite: big-then-small vs small-then-big. On raw prices this would
        # read near +1; on returns it is -1.
        assert correlation([100, 200, 210], [100, 105, 210]) == pytest.approx(-1.0)

    def test_symmetric(self):
        a, b = [100, 103, 101, 106, 104], [50, 51, 49, 52, 53]
        assert correlation(a, b) == pytest.approx(correlation(b, a))
        assert -1.0 <= correlation(a, b) <= 1.0

    def test_flat_series_is_none(self):
        assert correlation([10, 10, 10], [1, 2, 3]) is None

    def test_steady_growth_is_none(self):
        # Constant returns: no variance, so correlation is undefined.
        assert correlation([1, 2, 4], [5, 6, 4]) is None

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="same length"):
            correlation([1, 2, 3], [1, 2, 3, 4])

    def test_too_few_prices_raises(self):
        with pytest.raises(ValueError, match="at least 3 prices"):
            correlation([1, 2], [3, 4])

    def test_zero_price_raises(self):
        with pytest.raises(ValueError, match="non-zero"):
            correlation([1, 0, 3], [1, 2, 3])
