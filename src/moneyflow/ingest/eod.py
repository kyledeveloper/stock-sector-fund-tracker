"""EOD market-data adapter (M3). Phase 0 PoC picks the provider.

Candidates: Stooq daily CSV (no key, $0) vs Tiingo (free tier needs signup
token; 500 symbols/mo, 50 req/hr -- plenty for 12 tickers).
Finnhub free is OUT: /stock/candle returns 403 on free tier (verified).
PoC must prove 90-day backfill for 12 tickers in a handful of requests.
"""

from moneyflow.ingest.base import SourceAdapter


class EodAdapter(SourceAdapter):
    name = "eod"

    def fetch_raw(self) -> bytes:
        raise NotImplementedError("Phase 0 PoC picks provider")

    def parse(self, raw: bytes):
        raise NotImplementedError("Phase 0 PoC picks provider")
