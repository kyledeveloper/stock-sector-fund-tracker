"""Contract tests: the facts PLAN.md pins down."""

from datetime import date

import pytest
from pydantic import ValidationError

from moneyflow.models import BENCHMARK, SECTOR_ETFS, Holding, SectorFlow


def test_sector_etf_universe_is_11_gics_sectors():
    assert len(SECTOR_ETFS) == 11
    assert len(set(SECTOR_ETFS)) == 11  # no duplicates (XLC was doubled once)
    assert "XLB" in SECTOR_ETFS  # materials must not be dropped again
    assert BENCHMARK == "SPY"


def test_flow_to_aum_normalizes_price_effects():
    f = SectorFlow(as_of=date(2026, 9, 30), ticker="XLF", net_flow_usd=1e8, aum_usd=1e10)
    assert f.flow_to_aum == 0.01


def test_flow_to_aum_none_without_aum():
    f = SectorFlow(as_of=date(2026, 9, 30), ticker="XLF", net_flow_usd=1e8)
    assert f.flow_to_aum is None


def test_holding_allows_small_negative_weight_for_futures_hedge():
    # Real SSGA file, 2026-10-01: XLF holds "XAF FINANCIAL DEC26" (IXAZ6)
    # at -0.010097% -- a short futures hedge, not a data error.
    h = Holding(
        as_of=date(2026, 10, 1),
        etf_ticker="XLF",
        ticker="IXAZ6",
        name="XAF FINANCIAL DEC26",
        weight=-0.00010097,
    )
    assert h.weight == pytest.approx(-0.00010097)


def test_holding_rejects_implausible_negative_weight():
    with pytest.raises(ValidationError):
        Holding(
            as_of=date(2026, 10, 1),
            etf_ticker="XLF",
            ticker="XXX",
            weight=-0.5,
        )
