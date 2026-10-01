"""Cross-sector exposure compute tests (M2, v1 redefined).

stock_exposure is pure: holdings in, exposures out. No I/O, no DB,
no HTTP -- the signature test below pins that.
"""

from __future__ import annotations

import inspect
from datetime import date

import pytest

from moneyflow.compute.exposure import stock_exposure
from moneyflow.models import Holding

AS_OF = date(2026, 9, 30)


def _h(etf: str, ticker: str, weight: float) -> Holding:
    return Holding(as_of=AS_OF, etf_ticker=etf, ticker=ticker, name=ticker, weight=weight)


def test_cross_sector_weights_are_summed_not_double_counted():
    hs = [
        _h("XLC", "GOOGL", 0.10),
        _h("XLY", "GOOGL", 0.05),  # same stock, two sector ETFs
        _h("XLK", "NVDA", 0.15),
    ]
    out = stock_exposure(hs, AS_OF)
    by = {e.ticker: e for e in out}
    assert by["GOOGL"].total_weight == pytest.approx(0.15)
    assert by["GOOGL"].etf_count == 2
    assert set(by["GOOGL"].contributing_etfs) == {"XLC", "XLY"}
    assert by["NVDA"].total_weight == pytest.approx(0.15)
    assert by["NVDA"].etf_count == 1


def test_output_sorted_by_weight_desc():
    hs = [_h("XLK", "AAA", 0.01), _h("XLK", "BBB", 0.20)]
    out = stock_exposure(hs, AS_OF)
    assert [e.ticker for e in out] == ["BBB", "AAA"]


def test_empty_in_empty_out():
    assert stock_exposure([], AS_OF) == []


def test_pure_function_signature():
    """No engine/session/client params: I/O cannot sneak in."""
    params = inspect.signature(stock_exposure).parameters
    assert set(params) == {"holdings", "as_of"}
