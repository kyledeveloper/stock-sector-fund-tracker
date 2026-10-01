"""SSGA official daily holdings adapter (M2). Phase 1.

URL pattern (red-team verified 2026-10-01):
  https://www.ssga.com/library-content/products/fund-data/etfs/us/
  holdings-daily-us-en-{ticker}.xlsx   (lowercase ticker)

Free, official, no ToS risk. Holdings file is T-1 vs flow date --
callers must align as-of dates (see compute/exposure.py).
"""

from moneyflow.ingest.base import SourceAdapter


class SsgaAdapter(SourceAdapter):
    name = "ssga"

    def fetch_raw(self) -> bytes:
        raise NotImplementedError("Phase 1")

    def parse(self, raw: bytes):
        raise NotImplementedError("Phase 1")
