"""M3 service + API tests: idempotent run, fail-loud batch validation,
freshness watchdog, and the /api/v1/momentum contract.

Synthetic bars for the 12 M3 tickers (11 sectors + SPY); no network.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from moneyflow.api.main import app
from moneyflow.api.routers import momentum as momentum_router
from moneyflow.models import BENCHMARK, SECTOR_ETFS, PriceBar
from moneyflow.services import m3 as m3_service
from moneyflow.services.freshness import get_freshness
from moneyflow.store.migrate import apply_migrations

client = TestClient(app)

D0 = date(2026, 9, 30)
N_BARS = 70


def _bars(ticker: str, last: date = D0, n: int = N_BARS, base: float = 100.0) -> list[PriceBar]:
    return [
        PriceBar(
            as_of=last - timedelta(days=n - 1 - i),
            ticker=ticker,
            close=base + i * 0.1,
            volume=1000,
        )
        for i in range(n)
    ]


def _universe(**overrides) -> dict[str, list[PriceBar]]:
    tickers = list(SECTOR_ETFS) + [BENCHMARK]
    out = {t: _bars(t) for t in tickers}
    out.update(overrides)
    return out


def _engine():
    engine = create_engine("sqlite://")
    apply_migrations(engine)
    return engine


def _counts(engine) -> tuple[int, int]:
    with engine.connect() as conn:
        b = conn.execute(text("SELECT COUNT(*) FROM price_bar")).scalar()
        m = conn.execute(text("SELECT COUNT(*) FROM sector_momentum")).scalar()
    return b, m


def test_run_m3_writes_bars_momentum_and_freshness():
    engine = _engine()
    result = m3_service.run_m3(engine, bars_by_ticker=_universe())
    assert result["as_of"] == D0
    n_bars, n_mom = _counts(engine)
    assert n_bars == 12 * N_BARS
    assert n_mom == 11  # sectors only; SPY is the benchmark
    rows = {f.module: f for f in get_freshness(engine, today=date(2026, 10, 1))}
    assert rows["m3"].as_of == D0
    assert rows["m3"].stale is False


def test_run_m3_twice_is_idempotent():
    engine = _engine()
    m3_service.run_m3(engine, bars_by_ticker=_universe())
    before = _counts(engine)
    m3_service.run_m3(engine, bars_by_ticker=_universe())
    assert _counts(engine) == before


def test_mixed_latest_dates_fail_loud_and_write_nothing():
    """B1 lesson applied to M3: all tickers must agree on the latest bar date."""
    engine = _engine()
    bad = _universe(XLK=_bars("XLK", last=D0 - timedelta(days=1)))
    with pytest.raises(ValueError, match="mixed latest bar dates"):
        m3_service.run_m3(engine, bars_by_ticker=bad)
    assert _counts(engine) == (0, 0)


def test_too_few_bars_fail_loud():
    engine = _engine()
    bad = _universe(XLK=_bars("XLK", n=30))
    with pytest.raises(ValueError, match="XLK"):
        m3_service.run_m3(engine, bars_by_ticker=bad)


@pytest.fixture()
def seeded_engine(monkeypatch, tmp_path):
    # File DB, not :memory:: TestClient serves requests on another thread.
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    apply_migrations(eng)
    monkeypatch.setattr(momentum_router, "_engine", lambda: eng)
    m3_service.run_m3(eng, bars_by_ticker=_universe())
    return eng


def test_momentum_api_returns_ranked_sectors(seeded_engine):
    body = client.get("/api/v1/momentum").json()
    assert len(body) == 11
    assert {r["ticker"] for r in body} == set(SECTOR_ETFS)
    assert all(r["as_of"] == "2026-09-30" for r in body)
    rs = [r["rs_20d"] for r in body]
    assert rs == sorted(rs, reverse=True)
    assert all(r["rrg_quadrant"] in {"leading", "weakening", "lagging", "improving"} for r in body)
    assert all("SPY" != r["ticker"] for r in body)


def test_momentum_api_empty_db_returns_empty_list(monkeypatch, tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/e.db")
    apply_migrations(eng)
    monkeypatch.setattr(momentum_router, "_engine", lambda: eng)
    assert client.get("/api/v1/momentum").json() == []
