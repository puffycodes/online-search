"""Tests for indicators: the price-series transforms, trend classifier, and _ols_slope."""

import pytest

from indicators import (
    _ols_slope,
    moving_average,
    moving_average_cross,
    moving_average_cross_flip,
    price_vs_moving_average,
    rebase,
    trend,
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
