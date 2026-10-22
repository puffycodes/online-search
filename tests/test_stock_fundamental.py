"""Tests for stock_fundamental: indicator extraction, output, main().

The Yahoo parsing behind stock_data.fundamentals_view() (the gross-margin and
debt/equity conventions among them) is tested in test_yahoo_finance.py; here
every view is already in stock_data's neutral shape.
"""

import json

import pytest
import requests

import stock_data
import stock_fundamental as sf
import stock_intrinsic_value as siv

VIEW_KEYS = (
    "source", "notes", "name", "exchange", "currency", "sector", "industry", "price",
    "market_cap", "shares_outstanding", "free_cash_flow", "operating_cash_flow", "ebitda",
    "revenue", "net_income", "total_debt", "total_cash", "eps_ttm", "eps_forward",
    "book_value_per_share", "beta", "trailing_pe", "forward_pe", "price_to_sales",
    "price_to_book", "enterprise_value", "ev_to_ebitda", "gross_margin", "operating_margin",
    "net_margin", "return_on_equity", "return_on_assets", "revenue_growth", "earnings_growth",
    "debt_to_equity", "current_ratio", "quick_ratio", "dividend_per_share", "payout_ratio",
    "analyst_growth_1y", "analyst_growth_5y",
)


def _view(**changes):
    """A minimal neutral view: what collect_inputs needs, everything else None."""
    view = dict.fromkeys(VIEW_KEYS)
    view.update({
        "source": "Test", "notes": [],
        "name": "Triple A Inc.", "exchange": "TST", "currency": "USD",
        "sector": "Technology", "industry": "Consumer Electronics",
        "price": 100.0, "shares_outstanding": 1e9, "free_cash_flow": 5e9, "ebitda": 8e9,
        "revenue": 40e9, "total_debt": 2e9, "total_cash": 1e9, "eps_ttm": 5.0, "beta": 1.0,
        "trailing_pe": 20.0, "price_to_sales": 2.5, "enterprise_value": 101e9,
        "ev_to_ebitda": 12.0, "dividend_per_share": 2.0,
    })
    view.update(changes)
    return view


def _full_view(**changes):
    """_view() plus every field extract_indicators reads directly."""
    return _view(
        market_cap=100e9, gross_margin=0.45, operating_margin=0.3, net_margin=0.25,
        return_on_equity=1.5, return_on_assets=0.2, revenue_growth=0.08,
        earnings_growth=-0.02, debt_to_equity=1.5, current_ratio=0.9, quick_ratio=0.8,
        operating_cash_flow=7e9, price_to_book=40.0, net_income=4e9, forward_pe=18.0,
        payout_ratio=0.4, analyst_growth_5y=0.1, **changes,
    )


def _indicators(view):
    return sf.extract_indicators(view, siv.collect_inputs(view))


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
        assert _indicators(_full_view()) == {
            "gross_margin": 0.45, "operating_margin": 0.3, "net_margin": 0.25,
            "return_on_equity": 1.5, "return_on_assets": 0.2,
            "revenue_growth": 0.08, "earnings_growth": -0.02, "analyst_growth_5y": 0.1,
            "trailing_pe": 20.0, "forward_pe": 18.0,
            "peg": pytest.approx(2.0),            # 20 P/E / 10% growth
            "ev_to_ebitda": 12.0, "price_to_book": 40.0, "price_to_sales": 2.5,
            "fcf_yield": pytest.approx(0.05),     # 5B FCF / 100B market cap
            "debt_to_equity": 1.5,
            "net_debt_to_ebitda": pytest.approx(0.125),  # (2B - 1B) / 8B
            "current_ratio": 0.9, "quick_ratio": 0.8,
            "free_cash_flow": 5e9, "operating_cash_flow": 7e9,
            "cash_conversion": pytest.approx(1.25),  # 5B FCF / 4B net income
            "dividend_yield": pytest.approx(0.02),   # 2.0 per share / 100.0 price
            "payout_ratio": 0.4,
        }

    def test_every_grouped_key_is_extracted(self):
        keys = [key for _, rows in sf.INDICATOR_GROUPS for key, _, _ in rows]
        assert sorted(keys) == sorted(_indicators(_view()))

    def test_missing_fields_are_none(self):
        out = _indicators(_view())
        for key in ("gross_margin", "return_on_equity", "revenue_growth", "price_to_book",
                    "debt_to_equity", "current_ratio", "operating_cash_flow", "payout_ratio",
                    "peg", "fcf_yield", "cash_conversion", "analyst_growth_5y"):
            assert out[key] is None, key

    def test_not_meaningful_ratios_are_none(self):
        out = _indicators(_view(ebitda=-1e9, net_income=-2e9, analyst_growth_5y=-0.05))
        assert out["net_debt_to_ebitda"] is None  # negative EBITDA
        assert out["cash_conversion"] is None     # negative net income
        assert out["peg"] is None                 # negative growth

    def test_net_cash_gives_negative_net_debt_to_ebitda(self):
        assert _indicators(_view(total_cash=6e9))["net_debt_to_ebitda"] == pytest.approx(-0.5)

    def test_non_payer_has_no_dividend_yield(self):
        assert _indicators(_view(dividend_per_share=None))["dividend_yield"] is None


class TestOutput:
    def test_build_json_shape(self):
        view = _full_view()
        inputs = siv.collect_inputs(view)
        indicators = sf.extract_indicators(view, inputs)
        out = sf.build_json("AAA", inputs, indicators)
        assert out == {
            "symbol": "AAA", "name": "Triple A Inc.", "exchange": "TST", "currency": "USD",
            "sector": "Technology", "industry": "Consumer Electronics",
            "price": 100.0, "market_cap": 100e9, "indicators": indicators,
        }
        json.dumps(out)

    def test_build_report_sections(self):
        view = _full_view()
        inputs = siv.collect_inputs(view)
        report = sf.build_report("AAA", inputs, sf.extract_indicators(view, inputs))
        assert report.startswith("AAA - Triple A Inc.  (TST - USD)")
        for group, rows in sf.INDICATOR_GROUPS:
            assert f"\n{group}\n" in report
            for _, label, _ in rows:
                assert label in report
        assert "45.00%" in report     # gross margin as a percentage
        assert "5.00B" in report      # free cash flow abbreviated
        assert "1.50" in report       # debt/equity as a ratio

    def test_build_report_missing_shows_dash(self):
        inputs = siv.collect_inputs(_view())
        report = sf.build_report("AAA", inputs, sf.extract_indicators(_view(), inputs))
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
        monkeypatch.setattr(stock_data, "fundamentals_view",
                            lambda s: seen.append(s) or _full_view())
        sf.main(["aaa", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert seen == ["aaa"]
        assert out["symbol"] == "AAA"  # upper-cased
        assert out["indicators"]["debt_to_equity"] == 1.5
        assert "source" not in out

    def test_text_output(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "fundamentals_view", lambda s: _view())
        sf.main(["AAA"])
        assert "Profitability" in capsys.readouterr().out

    def test_fetch_error_exits_1_json(self, monkeypatch, capsys):
        def boom(symbol):
            raise requests.RequestException("Quote not found")

        monkeypatch.setattr(stock_data, "fundamentals_view", boom)
        with pytest.raises(SystemExit) as exc:
            sf.main(["ZZZ", "--json"])
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().err) == {
            "error": "failed to fetch fundamentals for 'ZZZ': Quote not found"}

    def test_no_price_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(stock_data, "fundamentals_view", lambda s: _view(price=None))
        with pytest.raises(SystemExit) as exc:
            sf.main(["AAA"])
        assert exc.value.code == 1
        assert "no usable fundamentals" in capsys.readouterr().err

    def test_unknown_flag_exits_2_before_fetch(self, monkeypatch):
        monkeypatch.setattr(stock_data, "fundamentals_view",
                            lambda s: pytest.fail("should not fetch"))
        with pytest.raises(SystemExit) as exc:
            sf.main(["AAA", "--bogus"])
        assert exc.value.code == 2
