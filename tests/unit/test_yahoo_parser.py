"""Yahoo chart parser contract tests (M3).

Golden fixture: tests/fixtures/yahoo/xlk_chart.json -- the real
Yahoo response for XLK captured 2026-10-01 (64 daily bars,
2026-07-02 -> 2026-10-01). No network in these tests.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from moneyflow.ingest.eod import YahooEodAdapter

FIXTURE = Path(__file__).parents[1] / "fixtures" / "yahoo" / "xlk_chart.json"
ET = ZoneInfo("America/New_York")

# Fixture was fetched 2026-10-01 ~18:55 ET, after the 16:00 close.
AFTER_CLOSE = datetime(2026, 10, 1, 18, 55, tzinfo=ET)
MID_SESSION = datetime(2026, 10, 1, 12, 0, tzinfo=ET)


def _parse(now: datetime) -> list:
    return YahooEodAdapter("XLK", now=now).parse(FIXTURE.read_bytes())


def test_parses_real_xlk_chart_shape():
    bars = _parse(AFTER_CLOSE)
    assert len(bars) == 64
    assert all(b.ticker == "XLK" for b in bars)
    assert bars[0].as_of == date(2026, 7, 2)
    assert bars[-1].as_of == date(2026, 10, 1)
    assert bars[-1].close == 197.80999755859375  # adj close from the real payload
    assert all(b.volume >= 0 for b in bars)
    assert [b.as_of for b in bars] == sorted(b.as_of for b in bars)


def test_drops_still_forming_today_bar_mid_session():
    """Red-team M5: a bar for today while the session is open is dropped."""
    bars = _parse(MID_SESSION)
    assert len(bars) == 63
    assert bars[-1].as_of == date(2026, 9, 30)


def test_keeps_completed_today_bar_after_close():
    bars = _parse(AFTER_CLOSE)
    assert bars[-1].as_of == date(2026, 10, 1)


def test_drops_null_close_rows():
    payload = json.loads(FIXTURE.read_text())
    quote = payload["chart"]["result"][0]["indicators"]["quote"][0]
    quote["close"][10] = None
    adj = payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"]
    adj[10] = None
    bars = YahooEodAdapter("XLK", now=AFTER_CLOSE).parse(json.dumps(payload).encode())
    assert len(bars) == 63
    assert date(2026, 7, 17) not in {b.as_of for b in bars}


def test_prefers_adjusted_close():
    payload = json.loads(FIXTURE.read_text())
    adj = payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"]
    adj[-1] = 190.0  # simulate a distribution-adjusted close
    bars = YahooEodAdapter("XLK", now=AFTER_CLOSE).parse(json.dumps(payload).encode())
    assert bars[-1].close == 190.0


def test_error_payload_raises_loudly():
    raw = json.dumps(
        {"chart": {"result": None, "error": {"code": "Not Found", "description": "No data found"}}}
    ).encode()
    try:
        YahooEodAdapter("BOGUS", now=AFTER_CLOSE).parse(raw)
    except ValueError as e:
        assert "No data found" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_symbol_mismatch_raises_loudly():
    payload = json.loads(FIXTURE.read_text())  # payload says XLK
    try:
        YahooEodAdapter("XLF", now=AFTER_CLOSE).parse(json.dumps(payload).encode())
    except ValueError as e:
        assert "mismatch" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_short_adjclose_raises_loudly():
    """Red-team blocker-1: a truncated adjclose array must not silently mix
    adjusted and unadjusted closes in one series."""
    payload = json.loads(FIXTURE.read_text())
    adj = payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"]
    payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"] = adj[:-5]
    try:
        YahooEodAdapter("XLK", now=AFTER_CLOSE).parse(json.dumps(payload).encode())
    except ValueError as e:
        assert "adjclose" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_duplicate_timestamps_raise_loudly():
    """Red-team blocker-2: duplicate bar timestamps must not be silently
    collapsed (last-wins) downstream."""
    payload = json.loads(FIXTURE.read_text())
    res = payload["chart"]["result"][0]
    res["timestamp"].append(res["timestamp"][-1])
    for key in ("close", "volume"):
        res["indicators"]["quote"][0][key].append(999.0)
    res["indicators"]["adjclose"][0]["adjclose"].append(999.0)
    try:
        YahooEodAdapter("XLK", now=AFTER_CLOSE).parse(json.dumps(payload).encode())
    except ValueError as e:
        assert "duplicate" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_naive_now_rejected():
    """Red-team minor-1: naive datetimes silently defeat the M5 gate."""
    from datetime import datetime as dt

    try:
        YahooEodAdapter("XLK", now=dt(2026, 10, 1, 18, 55)).parse(FIXTURE.read_bytes())
    except ValueError as e:
        assert "timezone-aware" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_null_adjclose_with_valid_raw_close_raises_loudly():
    """M2 (review 2026-10-02): a single null adjclose with a valid raw
    close must not silently fall back to the raw close (mixing adjusted
    and unadjusted prices in one series). Unlike test_drops_null_close_rows
    (both null -> drop), this mixed case fails loud."""
    payload = json.loads(FIXTURE.read_text())
    adj = payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"]
    adj[10] = None  # raw close at index 10 stays valid
    try:
        YahooEodAdapter("XLK", now=AFTER_CLOSE).parse(json.dumps(payload).encode())
    except ValueError as e:
        assert "adjclose" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for null adjclose with valid close")
