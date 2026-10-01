"""Contract test for GET /api/v1/freshness (red-team B3).

Pins the backend shape the React Panel shell consumes:
module / as_of / checked_at (ISO-8601 string) / stale.
If this test goes red, the frontend contract broke -- fix the API,
not the test.

Phase 1: the stub is replaced with DB reads; the engine is monkeypatched
so tests never touch the real data/moneyflow.db.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from moneyflow.api.main import app
from moneyflow.api.routers import exposure as exposure_router
from moneyflow.api.routers import freshness as freshness_router
from moneyflow.services import m2 as m2_service
from moneyflow.store.migrate import apply_migrations

client = TestClient(app)


@pytest.fixture()
def engine(monkeypatch, tmp_path):
    # File DB, not :memory:: TestClient serves requests on another thread
    # and SQLite :memory: is per-connection.
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    apply_migrations(eng)
    monkeypatch.setattr(freshness_router, "_engine", lambda: eng)
    monkeypatch.setattr(exposure_router, "_engine", lambda: eng)
    return eng


def test_freshness_shape_matches_frontend_contract(engine):
    resp = client.get("/api/v1/freshness")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list) and len(body) == 4
    modules = set()
    for rec in body:
        assert set(rec) == {"module", "as_of", "checked_at", "stale"}, rec
        modules.add(rec["module"])
        assert rec["as_of"] is None  # empty DB: no data yet
        assert rec["stale"] is True
        # checked_at must be an ISO-8601 string -- web/src/api/types.ts
        # mirrors Freshness.checked_at as string.
        datetime.fromisoformat(rec["checked_at"])
    assert modules == {"m2", "m3", "m4", "m5"}  # M1 cut from v1 (user D, 2026-10-01)


def test_freshness_reflects_m2_run(engine):
    from moneyflow.models import Holding

    holdings = [
        Holding(
            as_of=date(2026, 10, 2),
            etf_ticker="XLF",
            ticker="JPM",
            name="JPMORGAN",
            weight=1.0,  # single holding = 100%; run_m2 gates per-ETF sums to ~1.0
        )
    ]
    m2_service.run_m2(engine, holdings=holdings, as_of=date(2026, 10, 2))
    body = {r["module"]: r for r in client.get("/api/v1/freshness").json()}
    assert body["m2"]["as_of"] == "2026-10-02"
