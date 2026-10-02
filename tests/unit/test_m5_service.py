"""M5 service tests: run_m5 write/skip, backfill weekend skip + error isolation.

No real network anywhere: PoliteClient is built on an httpx.MockTransport
with trust_env=False (sandbox proxy env would otherwise break it).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from freezegun import freeze_time
from sqlalchemy import create_engine

from moneyflow.common.http import PoliteClient
from moneyflow.common.trading_day import is_trading_day, today_et
from moneyflow.services import cboe as m5_service
from moneyflow.store.db import SessionLocal
from moneyflow.store.migrate import apply_migrations
from moneyflow.store.repos import CboePutCallRepository, FreshnessRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cboe"
SAMPLE = (FIXTURES / "cboe_daily_sample.html").read_text(encoding="utf-8")
WEEKEND = (FIXTURES / "cboe_weekend_nodata.html").read_text(encoding="utf-8")


@pytest.fixture()
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/m5svc.db")
    apply_migrations(eng)
    return eng


def _mock_client(handler, interval_s: float = 0.0) -> PoliteClient:
    # interval_s=0 keeps tests fast; production default stays 2.0s.
    return PoliteClient(
        min_interval_s=interval_s,
        trust_env=False,
        transport=httpx.MockTransport(handler),
    )


def _repos(engine):
    session = SessionLocal(bind=engine)
    try:
        return CboePutCallRepository(session), FreshnessRepository(session).all()
    finally:
        session.close()


def test_run_m5_writes_row_and_marks_freshness(engine):
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text=SAMPLE)

    result = m5_service.run_m5(engine, trade_date=date(2026, 9, 30), client=_mock_client(handler))
    assert result["skipped"] is False
    assert result["total_put_call"] == pytest.approx(0.88)
    assert result["equity_put_call"] == pytest.approx(0.53)
    assert result["index_put_call"] == pytest.approx(1.03)
    # one request, to the dated daily page
    assert requested == [
        "https://www.cboe.com/markets/us/options/market-statistics/daily?dt=2026-09-30"
    ]
    repo, freshness = _repos(engine)
    latest = repo.latest()
    assert latest is not None and latest.trade_date == date(2026, 9, 30)
    assert freshness["m5"][0] == date(2026, 9, 30)  # mark(), not touch()


def test_run_m5_parse_none_skips_write(engine):
    """Weekend/holiday page (zero ratio rows) -> no write, only touch."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=WEEKEND)

    result = m5_service.run_m5(engine, trade_date=date(2026, 9, 27), client=_mock_client(handler))
    assert result["skipped"] is True
    repo, freshness = _repos(engine)
    assert repo.latest() is None  # never write a dirty row
    assert len(repo.series(365)) == 0
    assert "m5" in freshness and freshness["m5"][0] is None  # touch(): checked, no as_of


def test_run_m5_garbled_page_raises(engine):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>redesigned</body></html>")

    with pytest.raises(m5_service.CboeParseError):
        m5_service.run_m5(engine, trade_date=date(2026, 9, 30), client=_mock_client(handler))
    repo, _ = _repos(engine)
    assert repo.latest() is None  # fail-loud: nothing stored


@freeze_time("2026-10-03 12:00:00")  # Sat 08:00 ET: trailing 5-day window covers a weekend
def test_backfill_skips_weekends_before_requesting(engine):
    """Weekend dates are skipped by is_trading_day -- never even requested."""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        dt = date.fromisoformat(request.url.params["dt"])
        assert is_trading_day(dt), f"weekend {dt} should never be requested"
        return httpx.Response(200, text=SAMPLE)

    result = m5_service.run_backfill_m5(engine, days=5, client=_mock_client(handler))
    assert result["errors"] == []
    assert result["fetched"] + result["skipped"] == 5
    assert result["skipped"] >= 1  # at least one weekend day in any 5-day window
    assert len(requested) == result["fetched"]  # skipped days cost zero requests
    # every requested dt was a trading day and got stored
    stored = {r.trade_date.isoformat() for r in _repos(engine)[0].series(365)}
    assert stored == {httpx.URL(u).params["dt"] for u in requested}
    assert len(stored) == result["fetched"]


def test_backfill_single_day_failure_does_not_abort(engine):
    """One garbled day is recorded in errors; the rest still land."""
    from moneyflow.common.trading_day import last_trading_day_before

    bad_day = last_trading_day_before(today_et()).isoformat()
    window = [today_et() - timedelta(days=b) for b in range(3)]
    trading_in_window = sum(1 for d in window if is_trading_day(d))
    assert bad_day in {d.isoformat() for d in window if is_trading_day(d)}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["dt"] == bad_day:
            return httpx.Response(200, text="<html>garbled</html>")
        return httpx.Response(200, text=SAMPLE)

    result = m5_service.run_backfill_m5(engine, days=3, client=_mock_client(handler))
    assert len(result["errors"]) == 1
    assert result["errors"][0]["trade_date"] == bad_day
    assert "CboeParseError" in result["errors"][0]["error"]
    assert result["fetched"] == trading_in_window - 1  # the rest still stored
    repo, _ = _repos(engine)
    assert len(repo.series(365)) == trading_in_window - 1


def test_backfill_upsert_failure_isolated_and_recorded(engine, monkeypatch):
    """A DB write failure on one day is recorded in errors; the backfill
    continues with the remaining days (red-team M2)."""
    from moneyflow.common.trading_day import last_trading_day_before

    bad_day = last_trading_day_before(today_et())
    real_upsert = m5_service.CboePutCallRepository.upsert

    def flaky_upsert(self, day):
        if day.trade_date == bad_day:
            raise RuntimeError("transient SQLite lock")
        return real_upsert(self, day)

    monkeypatch.setattr(m5_service.CboePutCallRepository, "upsert", flaky_upsert)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SAMPLE)

    result = m5_service.run_backfill_m5(engine, days=3, client=_mock_client(handler))
    assert len(result["errors"]) == 1
    assert result["errors"][0]["trade_date"] == bad_day.isoformat()
    assert "upsert RuntimeError" in result["errors"][0]["error"]
    window = [today_et() - timedelta(days=b) for b in range(3)]
    trading_in_window = sum(1 for d in window if is_trading_day(d))
    assert result["fetched"] == trading_in_window - 1
    repo, _ = _repos(engine)
    stored = {r.trade_date for r in repo.series(365)}
    assert bad_day not in stored
    assert len(stored) == trading_in_window - 1


def test_backfill_marks_freshness(engine):
    """After backfill, the m5 freshness row reflects the latest fetched
    date -- otherwise the panel grays out as 'unknown' (red-team M3)."""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text=SAMPLE)

    result = m5_service.run_backfill_m5(engine, days=5, client=_mock_client(handler))
    assert result["fetched"] >= 1
    session = SessionLocal(bind=engine)
    try:
        rec = FreshnessRepository(session).all().get("m5")
    finally:
        session.close()
    assert rec is not None
    repo, _ = _repos(engine)
    latest = max(r.trade_date for r in repo.series(365))
    assert rec[0] == latest
    assert rec[1] is not None  # checked_at bumped
