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


def test_api_putcall_not_implemented_yet():
    """Pre-GREEN: the endpoint does not exist -> 404 (empty state)."""
    from fastapi.testclient import TestClient

    from moneyflow.api.main import app

    resp = TestClient(app).get("/api/v1/sentiment/putcall?days=90")
    assert resp.status_code == 404
