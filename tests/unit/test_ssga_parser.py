"""SSGA parser contract test (Phase 1, red-team M3 golden fixture).

The fixture is a REAL SSGA payload saved 2026-10-01
(XLK holdings, "As of 30-Sep-2026", 22,971 bytes).
If SSGA changes the layout, this test goes red -- fix the parser,
never the test.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from moneyflow.ingest.ssga import SsgaAdapter

FIXTURE = Path(__file__).parents[1] / "fixtures" / "ssga" / "xlk_20260930.xlsx"


def _holdings():
    return SsgaAdapter("XLK").parse(FIXTURE.read_bytes())


def test_parses_real_xlk_holdings_shape():
    hs = _holdings()
    # 75 securities observed 2026-10-01: 77 ticker rows minus 2 cash
    # placeholder rows (ticker "-"), trailing blanks and footnote skipped.
    assert len(hs) == 75
    assert all(h.as_of == date(2026, 9, 30) for h in hs)
    assert all(h.etf_ticker == "XLK" for h in hs)
    assert all(h.ticker and h.ticker != "-" for h in hs)
    assert all(-0.01 <= h.weight <= 1 for h in hs)  # percent -> fraction


def test_cash_placeholder_rows_are_skipped():
    tickers = {h.ticker for h in _holdings()}
    assert "-" not in tickers


def test_first_holding_matches_observed_values():
    nvda = _holdings()[0]
    assert nvda.ticker == "NVDA"
    assert nvda.name == "NVIDIA CORP"
    assert abs(nvda.weight - 0.15472876) < 1e-8


def test_weights_sum_to_one():
    """Data-quality invariant: one ETF's weights partition ~100%."""
    hs = _holdings()
    assert abs(sum(h.weight for h in hs) - 1.0) < 0.001


def test_ticker_guard_rejects_mismatched_file():
    raw = FIXTURE.read_bytes()
    with pytest.raises(ValueError, match="XLK"):
        SsgaAdapter("XLF").parse(raw)


def test_duplicate_ticker_row_within_file_raises():
    """Red-team M5: a glitched file repeating a ticker must fail loud,
    never double-count its weight."""
    from io import BytesIO

    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(FIXTURE.read_bytes()))
    ws = wb["holdings"]
    ws.append(["NVIDIA CORP", "NVDA", "67066G104", "00000", 1.0])  # dup ticker
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError, match="duplicate ticker"):
        SsgaAdapter("XLK").parse(buf.getvalue())


def test_as_of_accepts_iso_fallback_format():
    """Red-team m2: tolerate a couple of plausible SSGA date formats."""
    from io import BytesIO

    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(FIXTURE.read_bytes()))
    wb["holdings"]["B3"] = "As of 2026-09-30"
    buf = BytesIO()
    wb.save(buf)
    hs = SsgaAdapter("XLK").parse(buf.getvalue())
    assert all(h.as_of == date(2026, 9, 30) for h in hs)
