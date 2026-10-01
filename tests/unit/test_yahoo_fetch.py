"""Yahoo chart fetch test via vcrpy.

The cassette (tests/fixtures/yahoo/cassettes/xlk_chart.yaml) wraps the
real Yahoo JSON response captured 2026-10-01 via curl -- the sandbox
proxy URL breaks httpx's trust_env parsing, so the cassette was built
by hand from the real body (recorded_with note inside). Afterwards the
test replays offline. If Yahoo changes the payload, rebuild the
cassette from a fresh curl capture.
"""

from __future__ import annotations

import vcr

from moneyflow.common.http import PoliteClient
from moneyflow.ingest.eod import YahooEodAdapter

_cassette = vcr.VCR(
    cassette_library_dir="tests/fixtures/yahoo/cassettes",
    record_mode="once",
    match_on=["method", "scheme", "host", "path"],
)


@_cassette.use_cassette("xlk_chart.yaml")
def test_fetch_real_xlk_chart_replays_offline():
    adapter = YahooEodAdapter("XLK", client=PoliteClient(trust_env=False, min_interval_s=0))
    raw = adapter.fetch_raw()
    assert raw[:14] == b'{"chart":{"res'


@_cassette.use_cassette("xlk_chart.yaml")
def test_fetch_then_parse_roundtrip():
    bars = YahooEodAdapter("XLK", client=PoliteClient(trust_env=False, min_interval_s=0)).fetch()
    assert len(bars) > 0
    assert all(b.ticker == "XLK" for b in bars)
