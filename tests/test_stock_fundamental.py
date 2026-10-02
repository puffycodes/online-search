"""Tests for stock_fundamental: indicator extraction, output, main()."""

import json

import pytest
import requests

import stock_fundamental as sf
import stock_intrinsic_value as siv


def _modules(price=100.0):
    """Minimal quoteSummary ``modules`` (the inputs stock_intrinsic_value.collect_inputs reads)."""
    return {
        "price": {"longName": "Triple A Inc.", "currency": "USD", "exchangeName": "TST",
                  "regularMarketPrice": {"raw": price}},
        "financialData": {"currentPrice": {"raw": price}, "freeCashflow": {"raw": 5e9},
                          "ebitda": {"raw": 8e9}, "totalDebt": {"raw": 2e9},
                          "totalCash": {"raw": 1e9}, "totalRevenue": {"raw": 40e9}},
        "defaultKeyStatistics": {"sharesOutstanding": {"raw": 1e9}, "trailingEps": {"raw": 5.0},
                                 "beta": {"raw": 1.0}, "enterpriseValue": {"raw": 101e9},
                                 "enterpriseToEbitda": {"raw": 12.0}},
        "summaryDetail": {"trailingPE": {"raw": 20.0}, "priceToSalesTrailing12Months": {"raw": 2.5},
                          "dividendRate": {"raw": 2.0}},
        "summaryProfile": {"sector": "Technology", "industry": "Consumer Electronics"},
    }


def _full_modules():
    """_modules() plus every field extract_indicators reads directly."""
    modules = _modules()
    modules["financialData"].update({
        "grossMargins": {"raw": 0.45}, "operatingMargins": {"raw": 0.3},
        "profitMargins": {"raw": 0.25}, "returnOnEquity": {"raw": 1.5},
        "returnOnAssets": {"raw": 0.2}, "revenueGrowth": {"raw": 0.08},
        "earningsGrowth": {"raw": -0.02}, "debtToEquity": {"raw": 150.0},
        "currentRatio": {"raw": 0.9}, "quickRatio": {"raw": 0.8},
        "operatingCashflow": {"raw": 7e9},
    })
    modules["defaultKeyStatistics"].update({
        "priceToBook": {"raw": 40.0}, "netIncomeToCommon": {"raw": 4e9},
    })
    modules["summaryDetail"].update({"forwardPE": {"raw": 18.0}, "payoutRatio": {"raw": 0.4}})
    modules["price"]["marketCap"] = {"raw": 100e9}
    modules["earningsTrend"] = {"trend": [{"period": "+5y", "growth": {"raw": 0.1}}]}
    return modules


def _indicators(modules):
    return sf.extract_indicators(modules, siv.collect_inputs(modules))


class TestRatio:
    @pytest.mark.parametrize("num,den,expected", [
        (1.0, 4.0, 0.25),
        (-1.0, 4.0, -0.25),  # a negative numerator is fine (e.g. net cash)
        (None, 4.0, None),
        (1.0, None, None),
        (1.0, 0.0, None),
        (1.0, -4.0, None),   # a non-positive denominator isn't meaningful
    ])
    def test_matrix(self, num, den, expected):
        assert sf._ratio(num, den) == expected


class TestExtractIndicators:
    def test_reads_and_derives_indicators(self):
        assert _indicators(_full_modules()) == {
            "gross_margin": 0.45, "operating_margin": 0.3, "net_margin": 0.25,
            "return_on_equity": 1.5, "return_on_assets": 0.2,
            "revenue_growth": 0.08, "earnings_growth": -0.02, "analyst_growth_5y": 0.1,
            "trailing_pe": 20.0, "forward_pe": 18.0,
            "peg": pytest.approx(2.0),            # 20 P/E / 10% growth
            "ev_to_ebitda": 12.0, "price_to_book": 40.0, "price_to_sales": 2.5,
            "fcf_yield": pytest.approx(0.05),     # 5B FCF / 100B market cap
            "debt_to_equity": 1.5,                # Yahoo's 150 (percent) -> 1.5x
            "net_debt_to_ebitda": pytest.approx(0.125),  # (2B - 1B) / 8B
            "current_ratio": 0.9, "quick_ratio": 0.8,
            "free_cash_flow": 5e9, "operating_cash_flow": 7e9,
            "cash_conversion": pytest.approx(1.25),  # 5B FCF / 4B net income
            "dividend_yield": pytest.approx(0.02),   # 2.0 / 100.0
            "payout_ratio": 0.4,
        }

    def test_every_grouped_key_is_extracted(self):
        keys = [key for _, rows in sf.INDICATOR_GROUPS for key, _, _ in rows]
        assert sorted(keys) == sorted(_indicators(_modules()))

    def test_missing_fields_are_none(self):
        out = _indicators(_modules())
        for key in ("gross_margin", "return_on_equity", "revenue_growth", "price_to_book",
                    "debt_to_equity", "current_ratio", "operating_cash_flow", "payout_ratio",
                    "peg", "fcf_yield", "cash_conversion", "analyst_growth_5y"):
            assert out[key] is None, key

    def test_not_meaningful_ratios_are_none(self):
        modules = _modules()
        modules["financialData"]["ebitda"] = {"raw": -1e9}
        modules["defaultKeyStatistics"]["netIncomeToCommon"] = {"raw": -2e9}
        modules["earningsTrend"] = {"trend": [{"period": "+5y", "growth": {"raw": -0.05}}]}
        out = _indicators(modules)
        assert out["net_debt_to_ebitda"] is None  # negative EBITDA
        assert out["cash_conversion"] is None     # negative net income
        assert out["peg"] is None                 # negative growth

    def test_zero_gross_margin_is_none(self):
        # Yahoo's placeholder for banks (no cost of goods sold), not a real 0% margin.
        modules = _modules()
        modules["financialData"]["grossMargins"] = {"raw": 0.0}
        assert _indicators(modules)["gross_margin"] is None

    def test_net_cash_gives_negative_net_debt_to_ebitda(self):
        modules = _modules()
        modules["financialData"]["totalCash"] = {"raw": 6e9}
        assert _indicators(modules)["net_debt_to_ebitda"] == pytest.approx(-0.5)


class TestOutput:
    def test_build_json_shape(self):
        modules = _full_modules()
        inputs = siv.collect_inputs(modules)
        indicators = sf.extract_indicators(modules, inputs)
        out = sf.build_json("AAA", inputs, indicators)
        assert out == {
            "symbol": "AAA", "name": "Triple A Inc.", "exchange": "TST", "currency": "USD",
            "sector": "Technology", "industry": "Consumer Electronics",
            "price": 100.0, "market_cap": 100e9, "indicators": indicators,
        }
        json.dumps(out)

    def test_build_report_sections(self):
        modules = _full_modules()
        inputs = siv.collect_inputs(modules)
        report = sf.build_report("AAA", inputs, sf.extract_indicators(modules, inputs))
        assert report.startswith("AAA - Triple A Inc.  (TST - USD)")
        for group, rows in sf.INDICATOR_GROUPS:
            assert f"\n{group}\n" in report
            for _, label, _ in rows:
                assert label in report
        assert "45.00%" in report     # gross margin as a percentage
        assert "5.00B" in report      # free cash flow abbreviated
        assert "1.50" in report       # debt/equity as a ratio

    def test_build_report_missing_shows_dash(self):
        inputs = siv.collect_inputs(_modules())
        report = sf.build_report("AAA", inputs, sf.extract_indicators(_modules(), inputs))
        line = next(l for l in report.splitlines() if "Payout ratio" in l)
        assert line.rstrip().endswith("-")


class TestParseArgs:
    def test_defaults(self):
        args = sf.parse_args(["AAPL"])
        assert (args.symbol, args.json) == ("AAPL", False)

    def test_missing_symbol_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            sf.parse_args([])
        assert exc.value.code == 2


class TestMain:
    def test_json_output(self, monkeypatch, capsys):
        seen = []
        monkeypatch.setattr(siv, "fetch_fundamentals", lambda s: seen.append(s) or _full_modules())
        sf.main(["aaa", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert seen == ["aaa"]
        assert out["symbol"] == "AAA"  # upper-cased
        assert out["indicators"]["debt_to_equity"] == 1.5

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(siv, "fetch_fundamentals", lambda s: _modules())
        sf.main(["AAA"])
        assert "Profitability" in capsys.readouterr().out

    def test_fetch_error_exits_1_json(self, monkeypatch, capsys):
        def boom(symbol):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(siv, "fetch_fundamentals", boom)
        with pytest.raises(SystemExit) as exc:
            sf.main(["ZZZ", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "failed to fetch fundamentals for 'ZZZ': Quote not found"}

    def test_no_price_exits_1(self, monkeypatch, capsys):
        modules = _modules()
        del modules["financialData"]["currentPrice"]
        del modules["price"]["regularMarketPrice"]
        monkeypatch.setattr(siv, "fetch_fundamentals", lambda s: modules)
        with pytest.raises(SystemExit) as exc:
            sf.main(["AAA"])
        assert exc.value.code == 1
        assert "no usable fundamentals" in capsys.readouterr().err

    def test_unknown_flag_exits_2_before_fetch(self, monkeypatch):
        monkeypatch.setattr(siv, "fetch_fundamentals", lambda s: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            sf.main(["AAA", "--bogus"])
        assert exc.value.code == 2
