"""CBOE daily put/call ratio adapter (M5). Phase 5.

Free daily CSVs on CBOE CDN, e.g. volume_and_call_put_ratios/totalpc.csv.
Known parse gotcha: 2-line preamble. PoC (Phase 0) must confirm CDN
reachability + ToS. Track total + equity scopes; index scope hedges vs
equity scope speculation often diverge -- document, don't blend.
"""

from moneyflow.ingest.base import SourceAdapter


class CboeAdapter(SourceAdapter):
    name = "cboe"

    def fetch_raw(self) -> bytes:
        raise NotImplementedError("Phase 5")

    def parse(self, raw: bytes):
        raise NotImplementedError("Phase 5")
