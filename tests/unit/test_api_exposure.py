"""Contract test for GET /api/v1/exposure (M2 panel data)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from moneyflow.api.main import app
from moneyflow.api.routers import exposure as exposure_router
from moneyflow.models import Holding
from moneyflow.services import m2 as m2_service
from moneyflow.store.migrate import apply_migrations

client = TestClient(app)


@pytest.fixture()
def engine(monkeypatch, tmp_path):
    # File DB, not :memory:: TestClient serves requests on another thread
    # and SQLite :memory: is per-connection.
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    apply_migrations(eng)
    monkeypatch.setattr(exposure_router, "_engine", lambda: eng)
    holdings = [
        # Synthetic holdings; each ETF's weights must sum to ~1.0 like a
        # real SSGA file (run_m2 enforces the per-ETF weight-sum gate).
        Holding(
            as_of=date(2026, 10, 2), etf_ticker="XLK", ticker="NVDA", name="NVIDIA", weight=0.60
        ),
        Holding(
            as_of=date(2026, 10, 2), etf_ticker="XLK", ticker="AAPL", name="APPLE", weight=0.40
        ),
        Holding(
            as_of=date(2026, 10, 2), etf_ticker="XLC", ticker="GOOGL", name="ALPHABET", weight=0.70
        ),
        Holding(as_of=date(2026, 10, 2), etf_ticker="XLC", ticker="META", name="META", weight=0.30),
        Holding(
            as_of=date(2026, 10, 2), etf_ticker="XLY", ticker="GOOGL", name="ALPHABET", weight=0.55
        ),
        Holding(
            as_of=date(2026, 10, 2), etf_ticker="XLY", ticker="AMZN", name="AMAZON", weight=0.45
        ),
    ]
    m2_service.run_m2(eng, holdings=holdings, as_of=date(2026, 10, 2))
    return eng


def test_exposure_returns_ranked_list(engine):
    body = client.get("/api/v1/exposure").json()
    assert [r["ticker"] for r in body] == ["GOOGL", "NVDA", "AMZN", "AAPL", "META"]
    assert body[0]["total_weight"] == pytest.approx(1.25)
    assert body[0]["etf_count"] == 2
    assert set(body[0]["contributing_etfs"]) == {"XLC", "XLY"}
    assert all(r["as_of"] == "2026-10-02" for r in body)


def test_exposure_limit_is_respected(engine):
    body = client.get("/api/v1/exposure?limit=1").json()
    assert len(body) == 1


def test_exposure_empty_db_returns_empty_list(engine):
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM stock_exposure"))
        conn.commit()
    assert client.get("/api/v1/exposure").json() == []
