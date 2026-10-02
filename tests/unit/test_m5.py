"""M5 (CBOE put/call) RED tests: parser contract + API/CLI presence.

TDD RED phase (Phase 4). moneyflow.services.cboe does not exist yet, so
every test here must FAIL (collection error counts as red). After GREEN
these pin the parser contract:

  - parse_cboe_daily(html, trade_date) -> CboeDaily | None is a PURE
    function: no network, no DB. Weekend/holiday pages (zero ratio rows)
    return None (no-data day -> skip write, never write a dirty row).
  - Any partial/garbled data FAILS LOUD (raise CboeParseError), never a
    silent wrong number: missing EQUITY row, "--" value, decimal-shift
    (e.g. 88 instead of 0.88) caught by the sanity bound.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cboe"
SAMPLE = (FIXTURES / "cboe_daily_sample.html").read_text(encoding="utf-8")
WEEKEND = (FIXTURES / "cboe_weekend_nodata.html").read_text(encoding="utf-8")


def _cboe():
    from moneyflow.services import cboe

    return cboe


def test_parse_real_page_total_and_equity():
    cboe = _cboe()
    out = cboe.parse_cboe_daily(SAMPLE, "2026-09-30")
    assert out is not None
    assert out.trade_date.isoformat() == "2026-09-30"
    assert out.total_put_call == pytest.approx(0.88)
    assert out.equity_put_call == pytest.approx(0.53)
    assert out.index_put_call == pytest.approx(1.03)


def test_parse_keeps_decimal_scale():
    """0.88 must stay 0.88 -- a percent-style 88 is corruption, not data."""
    cboe = _cboe()
    out = cboe.parse_cboe_daily(SAMPLE, "2026-09-30")
    assert out is not None
    assert out.total_put_call < 30  # sanity bound lives in the parser


def test_parse_weekend_page_returns_none():
    """Weekend/holiday page has zero ratio rows -> no-data day, skip write."""
    cboe = _cboe()
    assert cboe.parse_cboe_daily(WEEKEND, "2026-09-27") is None


def test_parse_missing_equity_row_fails_loud():
    cboe = _cboe()
    html = SAMPLE.replace("EQUITY PUT/CALL RATIO", "EQUITY PCR (renamed)")
    with pytest.raises(cboe.CboeParseError):
        cboe.parse_cboe_daily(html, "2026-09-30")


def test_parse_dash_value_fails_loud():
    cboe = _cboe()
    html = SAMPLE.replace(">0.88</td>", ">--</td>")
    with pytest.raises(cboe.CboeParseError):
        cboe.parse_cboe_daily(html, "2026-09-30")


def test_parse_structure_change_fails_loud():
    cboe = _cboe()
    with pytest.raises(cboe.CboeParseError):
        cboe.parse_cboe_daily("<html><body>redesigned, no ratios</body></html>", "2026-09-30")


def test_parse_decimal_shift_fails_loud():
    """A 100x decimal shift (88.0 instead of 0.88) must raise, not store."""
    cboe = _cboe()
    html = SAMPLE.replace(">0.88</td>", ">88.0</td>")
    with pytest.raises(cboe.CboeParseError):
        cboe.parse_cboe_daily(html, "2026-09-30")


def test_parse_10x_decimal_shift_fails_loud():
    """A 10x decimal shift (8.8 instead of 0.88) must also raise, not store.

    Red-team M1: the old [0, 30] sanity bound let 10x/100x shifts through
    when they landed <= 30 (e.g. 0.25 -> 25.0). The [0, 5] bound catches
    them; this test pins that contract.
    """
    cboe = _cboe()
    html = SAMPLE.replace(">0.88</td>", ">8.8</td>")
    with pytest.raises(cboe.CboeParseError):
        cboe.parse_cboe_daily(html, "2026-09-30")


def test_parse_100x_shift_inside_old_bound_fails_loud():
    """0.25 -> 25.0: the case the old bound [0, 30] missed."""
    cboe = _cboe()
    html = SAMPLE.replace(">0.53</td>", ">25.0</td>")
    with pytest.raises(cboe.CboeParseError):
        cboe.parse_cboe_daily(html, "2026-09-30")


def _api_client(tmp_path, monkeypatch, rows):
    """TestClient against a seeded file-backed SQLite DB (TestClient serves
    on another thread, so :memory: is not usable -- same pattern as
    test_api_exposure)."""
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine

    from moneyflow.api.main import app
    from moneyflow.api.routers import sentiment as sentiment_router
    from moneyflow.models import CboeDaily
    from moneyflow.store.db import SessionLocal
    from moneyflow.store.migrate import apply_migrations
    from moneyflow.store.repos import CboePutCallRepository

    eng = create_engine(f"sqlite:///{tmp_path}/m5api.db")
    apply_migrations(eng)
    monkeypatch.setattr(sentiment_router, "_engine", lambda: eng)
    session = SessionLocal(bind=eng)
    try:
        repo = CboePutCallRepository(session)
        for trade_date, total in rows:
            repo.upsert(
                CboeDaily(
                    trade_date=trade_date,
                    total_put_call=total,
                    equity_put_call=round(total - 0.35, 2),
                    index_put_call=round(total + 0.15, 2),
                    fetched_at=datetime(2026, 9, 30, 21, 0, tzinfo=UTC),
                    source_url="https://www.cboe.com/markets/us/options/market-statistics/daily",
                )
            )
    finally:
        session.close()
    return TestClient(app)


def _last3():
    from moneyflow.common.trading_day import last_trading_day_before, today_et

    d0 = last_trading_day_before(today_et())
    d1 = last_trading_day_before(d0)
    return last_trading_day_before(d1), d1, d0


def test_api_putcall_returns_seeded_series(tmp_path, monkeypatch):
    """GREEN: the endpoint exists; oldest-first series, language-neutral."""
    d2, d1, d0 = _last3()
    client = _api_client(tmp_path, monkeypatch, [(d2, 0.90), (d1, 0.85), (d0, 0.88)])
    resp = client.get("/api/v1/sentiment/putcall")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["date"] for r in body["data"]] == [d2.isoformat(), d1.isoformat(), d0.isoformat()]
    assert set(body["data"][0]) == {"date", "total_put_call", "equity_put_call"}
    assert body["data"][-1]["total_put_call"] == pytest.approx(0.88)
    assert body["as_of"] == d0.isoformat()
    assert body["stale"] is False  # latest == last trading day before today


def test_api_putcall_stale_when_behind(tmp_path, monkeypatch):
    d2, _, _ = _last3()
    client = _api_client(tmp_path, monkeypatch, [(d2, 0.90)])
    body = client.get("/api/v1/sentiment/putcall").json()
    assert body["as_of"] == d2.isoformat()
    assert body["stale"] is True


def test_api_putcall_days_clamps_out_of_range(tmp_path, monkeypatch):
    """days=0 -> 1, days=9999 -> 365: clamp, never error."""
    d2, d1, d0 = _last3()
    client = _api_client(tmp_path, monkeypatch, [(d2, 0.90), (d1, 0.85), (d0, 0.88)])
    assert len(client.get("/api/v1/sentiment/putcall?days=0").json()["data"]) == 1
    assert len(client.get("/api/v1/sentiment/putcall?days=9999").json()["data"]) == 3
    assert len(client.get("/api/v1/sentiment/putcall?days=2").json()["data"]) == 2


def test_api_putcall_empty_db(tmp_path, monkeypatch):
    client = _api_client(tmp_path, monkeypatch, [])
    body = client.get("/api/v1/sentiment/putcall").json()
    assert body == {"data": [], "as_of": None, "stale": True}
