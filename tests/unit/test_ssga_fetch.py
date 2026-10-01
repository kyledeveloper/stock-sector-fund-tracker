"""SSGA fetch test via vcrpy (red-team m7: vcrpy earns its dependency).

The cassette is recorded ONCE from the real SSGA download; afterwards the
test replays offline. If SSGA changes the file, delete the cassette to
re-record. Binary XLSX body is stored by vcrpy as-is.
"""

from __future__ import annotations

import vcr

from moneyflow.common.http import PoliteClient
from moneyflow.ingest.ssga import SsgaAdapter

_cassette = vcr.VCR(
    cassette_library_dir="tests/fixtures/ssga/cassettes",
    record_mode="once",
    match_on=["method", "scheme", "host", "path"],
)


@_cassette.use_cassette("xlk_download.yaml")
def test_fetch_real_xlk_replays_offline():
    adapter = SsgaAdapter("XLK", PoliteClient(trust_env=False, min_interval_s=0))
    raw = adapter.fetch_raw()
    assert raw[:4] == b"PK\x03\x04"  # xlsx magic bytes
    assert len(raw) > 10_000


@_cassette.use_cassette("xlk_download.yaml")
def test_fetch_then_parse_roundtrip():
    holdings = SsgaAdapter("XLK", PoliteClient(trust_env=False, min_interval_s=0)).fetch()
    assert len(holdings) > 0
    assert all(h.etf_ticker == "XLK" for h in holdings)
