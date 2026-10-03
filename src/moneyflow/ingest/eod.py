"""Yahoo Finance chart API adapter for EOD bars (M3).

User decision 2026-10-01: Yahoo chart is the Phase 2 EOD source
(Tiingo free tier is the documented fallback). Unofficial endpoint,
no key, ToS gray area -- the user accepted this; no legal conclusion
is asserted here. Fetched at low frequency (12 tickers/day) with a
descriptive UA.

Endpoint (verified 2026-10-01):
  https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}?interval=1d&range=3mo

Red-team M5: the adapter drops the still-forming current-day bar --
momentum must never be computed on intraday prices. Completeness is
judged from the response's own currentTradingPeriod.regular.end
(honest for early closes), falling back to 16:00 ET.

Price choice: adjusted close (splits + dividends) when present --
relative strength on unadjusted closes is distorted by distributions.
"""

from __future__ import annotations

import json
from datetime import datetime, time
from zoneinfo import ZoneInfo

from moneyflow.common.http import PoliteClient
from moneyflow.ingest.base import SourceAdapter
from moneyflow.models import PriceBar

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
ET = ZoneInfo("America/New_York")
MARKET_CLOSE_FALLBACK = time(16, 0)


class YahooEodAdapter(SourceAdapter):
    name = "yahoo_eod"

    def __init__(
        self,
        ticker: str,
        range: str = "3mo",  # noqa: A002 - Yahoo's own query param name
        client: PoliteClient | None = None,
        now: datetime | None = None,
    ) -> None:
        self.ticker = ticker.upper()
        self.range = range
        # Lazy: parsing never needs HTTP, and building httpx.Client eagerly
        # would parse proxy env vars at import/test time.
        self._client = client
        self._owns_client = client is None
        # Injectable clock for tests (red-team M5 determinism). Must be
        # timezone-aware: a naive datetime would silently defeat the
        # incomplete-bar gate on non-ET systems (red-team minor-1).
        if now is not None:
            if now.tzinfo is None:
                raise ValueError("YahooEodAdapter now must be timezone-aware")
            now = now.astimezone(ET)
        self._now = now

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.ticker}?interval=1d&range={self.range}"

    def _live_client(self) -> PoliteClient:
        if self._client is None:
            self._client = PoliteClient()
        return self._client

    def fetch_raw(self) -> bytes:
        client = self._live_client()
        try:
            return client.get(self.url).content
        finally:
            if self._owns_client:
                client.close()
                self._client = None

    def parse(self, raw: bytes) -> list[PriceBar]:
        payload = json.loads(raw)
        chart = payload.get("chart", {})
        if chart.get("error"):
            raise ValueError(
                f"Yahoo {self.ticker}: {chart['error'].get('description', chart['error'])}"
            )
        results = chart.get("result")
        if not results:
            raise ValueError(f"Yahoo {self.ticker}: empty result")
        res = results[0]
        meta = res.get("meta", {})
        if (meta.get("symbol") or "").upper() != self.ticker:
            raise ValueError(
                f"Yahoo symbol mismatch: payload says {meta.get('symbol')!r}, "
                f"adapter expects {self.ticker!r}"
            )
        tz = ZoneInfo(meta.get("exchangeTimezoneName") or "America/New_York")
        now_et = self._now or datetime.now(ET)
        today = now_et.date()
        session_closed = _session_closed(meta, now_et)

        timestamps = res.get("timestamp") or []
        # Red-team blocker-2: duplicate timestamps would silently collapse
        # in the date-keyed dict downstream (last wins). Fail loud instead.
        if len(set(timestamps)) != len(timestamps):
            raise ValueError(f"Yahoo {self.ticker}: duplicate bar timestamps in payload")
        quote = (res.get("indicators", {}).get("quote") or [{}])[0]
        adj_raw = (res.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
        # Red-team blocker-1: a short adjclose array would silently mix
        # adjusted and unadjusted closes in one series. Fail loud on drift.
        if adj_raw is not None and len(adj_raw) != len(timestamps):
            raise ValueError(
                f"Yahoo {self.ticker}: adjclose length {len(adj_raw)} != "
                f"{len(timestamps)} timestamps (upstream schema drift)"
            )
        adj = adj_raw
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        bars: list[PriceBar] = []
        for i, ts in enumerate(timestamps):
            bar_date = datetime.fromtimestamp(ts, tz).date()
            if bar_date > today:
                continue  # future bar: never trust
            if bar_date == today and not session_closed:
                continue  # red-team M5: still-forming bar, drop it
            adj_close = adj[i] if adj and i < len(adj) else None
            raw_close = closes[i] if i < len(closes) else None
            if adj_close is None and raw_close is not None and adj:
                # M2 (review 2026-10-02): a single null adjclose with a valid
                # raw close must not silently fall back to the raw close --
                # that mixes adjusted and unadjusted prices in one series.
                # (adj entirely absent -> all-raw series, consistent; both
                # null -> padded non-trading day, dropped below.)
                raise ValueError(
                    f"Yahoo {self.ticker}: null adjclose for {bar_date}"
                    " with valid close (refusing to mix adjusted/unadjusted)"
                )
            close = adj_close if adj_close is not None else raw_close
            if close is None:
                continue  # Yahoo pads some non-trading days with nulls
            vol = volumes[i] if i < len(volumes) and volumes[i] else 0
            bars.append(
                PriceBar(
                    as_of=bar_date,
                    ticker=self.ticker,
                    close=float(close),
                    volume=int(vol),
                )
            )
        return bars


def _session_closed(meta: dict, now_et: datetime) -> bool:
    """True if today's regular session has ended (per Yahoo's own clock)."""
    try:
        end = meta["currentTradingPeriod"]["regular"]["end"]
        return now_et.timestamp() >= float(end)
    except (KeyError, TypeError, ValueError):
        return now_et.time() >= MARKET_CLOSE_FALLBACK
