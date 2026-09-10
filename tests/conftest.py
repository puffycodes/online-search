"""Shared pytest fixtures for the test suite. See tests/README.md."""

import pytest


@pytest.fixture
def chart_result():
    """A well-formed Yahoo chart ``result`` dict (one element of chart.result).

    Three settled daily bars for 2024-01-01 / 02 / 03 (UTC), with an adjclose
    block present.
    """
    return {
        "meta": {
            "symbol": "AAA",
            "fullExchangeName": "TestExchange",
            "currency": "USD",
            "gmtoffset": 0,
        },
        "timestamp": [1704067200, 1704153600, 1704240000],
        "indicators": {
            "quote": [
                {
                    "open": [10.0, 11.0, 12.0],
                    "high": [10.5, 11.5, 12.5],
                    "low": [9.5, 10.5, 11.5],
                    "close": [10.2, 11.2, 12.2],
                    "volume": [1000, 2000, 3000],
                }
            ],
            "adjclose": [{"adjclose": [10.1, 11.1, 12.1]}],
        },
    }
