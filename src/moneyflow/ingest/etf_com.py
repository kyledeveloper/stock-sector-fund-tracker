"""ETF.com daily fund-flow adapter (M1). Phase 0 PoC decides go/no-go.

RED FLAG (red team F1, verified 2026-10-01): the free daily page publishes
only market-wide Top 10 creations + Top 10 redemptions, NOT per-sector-ETF
daily flows. Do NOT implement against the Top-10 page as if it were full
coverage -- a silent data gap is worse than an error. PoC must confirm a
real per-ETF source (ETF profile pages / VettaFi / ETFdb) or M1 rescopes.
"""

from moneyflow.ingest.base import SourceAdapter


class EtfComAdapter(SourceAdapter):
    name = "etf_com"

    def fetch_raw(self) -> bytes:
        raise NotImplementedError("Phase 0 PoC pending")

    def parse(self, raw: bytes):
        raise NotImplementedError("Phase 0 PoC pending")
