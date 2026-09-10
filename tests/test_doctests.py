"""Keep the module-level doctests in the pure-logic modules wired into CI."""

import doctest

import indicators
import valuation


def test_indicators_doctests():
    results = doctest.testmod(indicators)
    assert results.failed == 0, results


def test_valuation_doctests():
    results = doctest.testmod(valuation)
    assert results.failed == 0, results
