"""M5 repository tests: upsert idempotency, series ordering/limit, latest."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine

from moneyflow.models import CboeDaily
from moneyflow.store.db import SessionLocal
from moneyflow.store.migrate import apply_migrations
from moneyflow.store.repos import CboePutCallRepository


@pytest.fixture()
def repo(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/m5.db")
    apply_migrations(eng)
    session = SessionLocal(bind=eng)
    yield CboePutCallRepository(session)
    session.close()


def _day(d: date, total: float) -> CboeDaily:
    return CboeDaily(
        trade_date=d,
        total_put_call=total,
        equity_put_call=round(total - 0.35, 2),
        index_put_call=round(total + 0.15, 2),
        fetched_at=datetime(2026, 9, 30, 21, 0, tzinfo=UTC),
        source_url="https://www.cboe.com/markets/us/options/market-statistics/daily?dt=2026-09-30",
    )


def test_upsert_is_idempotent(repo):
    repo.upsert(_day(date(2026, 9, 30), 0.88))
    repo.upsert(_day(date(2026, 9, 30), 0.95))  # same date, corrected values
    rows = repo.series(365)
    assert len(rows) == 1  # no duplicate row
    assert rows[0].total_put_call == pytest.approx(0.95)  # overwritten


def test_series_orders_asc_and_respects_limit(repo):
    for d, v in (
        (date(2026, 9, 30), 0.88),
        (date(2026, 9, 28), 0.90),
        (date(2026, 9, 29), 0.85),
    ):
        repo.upsert(_day(d, v))
    rows = repo.series(2)
    assert [r.trade_date.isoformat() for r in rows] == ["2026-09-28", "2026-09-29"]
    assert rows[0].total_put_call == pytest.approx(0.90)
    assert rows[0].source_url.startswith("https://www.cboe.com")
    assert rows[0].fetched_at is not None


def test_latest_returns_newest_or_none(repo):
    assert repo.latest() is None
    repo.upsert(_day(date(2026, 9, 28), 0.90))
    repo.upsert(_day(date(2026, 9, 30), 0.88))
    latest = repo.latest()
    assert latest is not None
    assert latest.trade_date == date(2026, 9, 30)
    assert latest.equity_put_call == pytest.approx(0.53)
    assert latest.index_put_call == pytest.approx(1.03)
