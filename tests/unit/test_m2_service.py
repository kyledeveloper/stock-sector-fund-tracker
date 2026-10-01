"""M2 service tests: idempotent re-run + freshness watchdog (Phase 1 DoD).

Uses the REAL XLK fixture for one ETF and synthetic holdings for a
second ETF; no network in these tests.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from freezegun import freeze_time
from sqlalchemy import create_engine

from moneyflow.common.trading_day import today_et
from moneyflow.ingest.ssga import SsgaAdapter
from moneyflow.models import Holding
from moneyflow.services import m2 as m2_service
from moneyflow.services.freshness import get_freshness
from moneyflow.store.migrate import apply_migrations

FIXTURE = Path(__file__).parents[1] / "fixtures" / "ssga" / "xlk_20260930.xlsx"
AS_OF = date(2026, 9, 30)


def _engine():
    engine = create_engine("sqlite://")
    apply_migrations(engine)
    return engine


def _holdings() -> list[Holding]:
    xlk = SsgaAdapter("XLK").parse(FIXTURE.read_bytes())
    xlf = [
        # Synthetic second ETF; weights must sum to ~1.0 like a real file
        # (run_m2 enforces the per-ETF weight-sum gate, red-team B2).
        Holding(as_of=AS_OF, etf_ticker="XLF", ticker="BRK-B", name="BERKSHIRE", weight=0.60),
        Holding(as_of=AS_OF, etf_ticker="XLF", ticker="JPM", name="JPMORGAN", weight=0.40),
    ]
    return xlk + xlf


def _counts(engine) -> tuple[int, int]:
    from sqlalchemy import text

    with engine.connect() as conn:
        h = conn.execute(text("SELECT COUNT(*) FROM holding")).scalar()
        e = conn.execute(text("SELECT COUNT(*) FROM stock_exposure")).scalar()
    return h, e


def test_run_m2_twice_is_idempotent():
    engine = _engine()
    first = m2_service.run_m2(engine, holdings=_holdings())
    assert first["as_of"] == AS_OF
    n_holdings, n_exposures = _counts(engine)
    assert n_holdings == len(_holdings())
    assert n_exposures > 0

    second = m2_service.run_m2(engine, holdings=_holdings())
    assert second == first  # same summary
    assert _counts(engine) == (n_holdings, n_exposures)  # no duplicates


def test_freshness_marks_m2_with_as_of():
    engine = _engine()
    friday = date(2026, 10, 2)
    m2_service.run_m2(engine, holdings=_holdings(), as_of=friday)
    rows = {f.module: f for f in get_freshness(engine, today=date(2026, 10, 5))}
    assert rows["m2"].as_of == friday
    assert rows["m2"].stale is False  # Monday: Friday data is latest
    assert rows["m3"].as_of is None and rows["m3"].stale is True


def test_stale_after_t_plus_1_gap():
    engine = _engine()
    friday = date(2026, 10, 2)
    m2_service.run_m2(engine, holdings=_holdings(), as_of=friday)
    rows = {f.module: f for f in get_freshness(engine, today=date(2026, 10, 6))}
    assert rows["m2"].stale is True  # Tuesday: Monday's data expected


@freeze_time("2026-10-03 12:00:00")  # Saturday, America/New_York wall time
def test_run_all_skips_write_on_non_trading_day(tmp_path):
    from moneyflow.pipeline.daily import run_all
    from moneyflow.store.db import get_engine

    engine = get_engine(tmp_path / "t.db")
    apply_migrations(engine)
    result = run_all(engine)
    assert result["skipped"] is True
    assert today_et() == date(2026, 10, 3)
    assert _counts(engine) == (0, 0)  # nothing written

    rows = {f.module: f for f in get_freshness(engine, today=date(2026, 10, 3))}
    assert rows["m2"].as_of is None  # checked_at bumped, as_of untouched


def test_run_m2_rejects_mixed_as_of_dates():
    """Red-team B1: a lagging ETF file must fail loud, never merge silently."""
    engine = _engine()
    lagging = [
        Holding(
            as_of=date(2026, 9, 29), etf_ticker="XLF", ticker="JPM", name="JPMORGAN", weight=1.0
        ),
    ]
    with pytest.raises(ValueError, match="mixed as_of"):
        m2_service.run_m2(engine, holdings=_holdings() + lagging)
    assert _counts(engine) == (0, 0)  # nothing written on rejection


def test_run_m2_rejects_weight_sum_drift():
    """Red-team B2: percent->fraction schema drift must fail loud."""
    engine = _engine()
    drifted = [
        Holding(
            as_of=AS_OF, etf_ticker="XLF", ticker="JPM", name="JPMORGAN", weight=0.0008
        ),  # file flipped to fractions
    ]
    with pytest.raises(ValueError, match="weights sum"):
        m2_service.run_m2(engine, holdings=drifted)
    assert _counts(engine) == (0, 0)


def test_fetch_failure_writes_nothing(monkeypatch):
    """Red-team M1: all-or-nothing is pinned -- one failed fetch, zero writes."""
    engine = _engine()

    def _boom():
        raise RuntimeError("SSGA 404 on one file")

    monkeypatch.setattr(m2_service, "_fetch_all", _boom)
    with pytest.raises(RuntimeError, match="404"):
        m2_service.run_m2(engine)
    assert _counts(engine) == (0, 0)
