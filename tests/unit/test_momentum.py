"""Sector momentum compute tests (M3). Pure function, no I/O.

Conventions pinned here:
- rs_Nd = N-day *excess* return vs SPY (fraction, not percent).
- Simplified RRG quadrant from (rs_60d, rs_20d); documented as a
  simplification, not the classic RS-Ratio/RS-Momentum.
- Needs 61 closes per ticker (t and t-60); fewer -> ValueError.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from moneyflow.compute.momentum import sector_momentum
from moneyflow.models import BENCHMARK, PriceBar

D0 = date(2026, 9, 30)


def _bars(ticker: str, closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(as_of=D0 - timedelta(days=len(closes) - 1 - i), ticker=ticker, close=c)
        for i, c in enumerate(closes)
    ]


def _flat(n: int, price: float = 100.0) -> list[float]:
    return [price] * n


def test_rs_is_excess_return_vs_spy():
    # Ticker doubles over 20d while SPY is flat -> rs_20d == 1.0
    ticker = _flat(40, 100.0) + [100.0] * 20 + [200.0]
    spy = _flat(61, 400.0)
    out = sector_momentum({"AAA": _bars("AAA", ticker), BENCHMARK: _bars(BENCHMARK, spy)})
    assert len(out) == 1
    assert out[0].rs_20d == pytest.approx(1.0)
    assert out[0].rrg_quadrant == "leading"


def test_rrg_quadrants():
    spy = _flat(61, 100.0)
    # leading: up over 60d and up over 20d
    lead = _flat(40, 100.0) + [110.0] * 20 + [121.0]
    # weakening: up over 60d but down over 20d
    weak = _flat(40, 100.0) + [130.0] * 20 + [117.0]
    # lagging: down over 60d and down over 20d
    lag = _flat(40, 100.0) + [90.0] * 20 + [81.0]
    # improving: down over 60d but up over 20d
    imp = _flat(40, 100.0) + [70.0] * 20 + [77.0]
    out = sector_momentum(
        {
            "LEAD": _bars("LEAD", lead),
            "WEAK": _bars("WEAK", weak),
            "LAG": _bars("LAG", lag),
            "IMP": _bars("IMP", imp),
            BENCHMARK: _bars(BENCHMARK, spy),
        }
    )
    by_ticker = {m.ticker: m for m in out}
    assert by_ticker["LEAD"].rrg_quadrant == "leading"
    assert by_ticker["WEAK"].rrg_quadrant == "weakening"
    assert by_ticker["LAG"].rrg_quadrant == "lagging"
    assert by_ticker["IMP"].rrg_quadrant == "improving"


def test_benchmark_excluded_from_output():
    bars = {"AAA": _bars("AAA", _flat(61, 100.0)), BENCHMARK: _bars(BENCHMARK, _flat(61, 400.0))}
    out = sector_momentum(bars)
    assert [m.ticker for m in out] == ["AAA"]


def test_output_sorted_by_rs_20d_desc():
    spy = _flat(61, 100.0)
    bars = {
        "LOW": _bars("LOW", _flat(61, 100.0)),
        "HIGH": _bars("HIGH", _flat(60, 100.0) + [150.0]),
        BENCHMARK: _bars(BENCHMARK, spy),
    }
    out = sector_momentum(bars)
    assert [m.ticker for m in out] == ["HIGH", "LOW"]
    assert out[0].as_of == D0


def test_insufficient_history_raises():
    bars = {"AAA": _bars("AAA", _flat(60, 100.0)), BENCHMARK: _bars(BENCHMARK, _flat(61, 400.0))}
    with pytest.raises(ValueError, match="AAA"):
        sector_momentum(bars)
