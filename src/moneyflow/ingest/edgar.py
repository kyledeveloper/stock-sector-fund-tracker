"""SEC EDGAR adapter (M4). Phase 4.

Compliance (non-negotiable):
- Descriptive User-Agent with contact info (see common/http.py)
- <= 10 req/s (we use 0.5s+ politeness sleeps -- far under)
- 13F-HR: quarterly, 45-day lag. Form 4: ~2-day lag. Show lags on the panel.

Scope (red team F4): a fixed manager watchlist decided in Phase 0,
NOT "all filers" -- full-market 13F diffing is its own project.
"""

from moneyflow.ingest.base import SourceAdapter


class EdgarAdapter(SourceAdapter):
    name = "edgar"

    def fetch_raw(self) -> bytes:
        raise NotImplementedError("Phase 4")

    def parse(self, raw: bytes):
        raise NotImplementedError("Phase 4")
