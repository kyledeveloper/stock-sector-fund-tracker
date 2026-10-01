"""Contract tests: the facts PLAN.md pins down."""

from datetime import date

from moneyflow.models import BENCHMARK, SECTOR_ETFS, SectorFlow


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
