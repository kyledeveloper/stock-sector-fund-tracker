"""M3 orchestration: Yahoo EOD bars -> sector momentum vs SPY (thin layer).

No business logic here: fetch via adapters, validate the batch,
pure compute, store via repositories, mark freshness.
Idempotent by upsert; fail-loud on bad batches (red-team B1/B3).

EOD source: Yahoo chart API (user decision 2026-10-01; Tiingo free
tier is the documented fallback). One request per ticker per run.
"""

from __future__ import annotations

from datetime import date

from moneyflow.common.http import PoliteClient
from moneyflow.compute.momentum import sector_momentum
from moneyflow.ingest.eod import YahooEodAdapter
from moneyflow.models import BENCHMARK, SECTOR_ETFS, PriceBar
from moneyflow.store.db import SessionLocal
from moneyflow.store.repos import (
    FreshnessRepository,
    PriceBarRepository,
    SectorMomentumRepository,
)

M3_TICKERS: tuple[str, ...] = tuple(SECTOR_ETFS) + (BENCHMARK,)
_MIN_BARS = 61  # matches compute.momentum: need t and t-60


def _fetch_all(range: str = "6mo") -> dict[str, list[PriceBar]]:  # noqa: A002
    # 6mo, not 3mo: a 3-month window over year-end holidays can dip to
    # ~60 bars, tripping the 61-bar gate and keeping the daily pipeline
    # red until the window slides (red-team minor-2). Same 12 requests.
    client = PoliteClient()
    try:
        out: dict[str, list[PriceBar]] = {}
        for ticker in M3_TICKERS:
            out[ticker] = YahooEodAdapter(ticker, range=range, client=client).fetch()
        return out
    finally:
        client.close()


def _validate_batch(bars_by_ticker: dict[str, list[PriceBar]]) -> date:
    """Fail-loud batch validation; returns the single agreed as_of date.

    B1 (Phase 1): every ticker must share one latest bar date. A lagging
    ticker merged under the majority date would silently corrupt the
    momentum snapshot, so mixed dates raise instead of being averaged.
    """
    if not bars_by_ticker:
        raise ValueError("M3: no bars to process")
    for ticker, bars in sorted(bars_by_ticker.items()):
        # Red-team minor-4: name the ticker instead of max() on empty.
        if not bars:
            raise ValueError(f"M3: {ticker} returned no bars (all dropped by parser?)")
    latest = {t: max(b.as_of for b in bars) for t, bars in bars_by_ticker.items()}
    dates = set(latest.values())
    if len(dates) > 1:
        divergent = ", ".join(f"{t}={d.isoformat()}" for t, d in sorted(latest.items()))
        raise ValueError(f"M3: mixed latest bar dates across tickers: {divergent}")
    for ticker, bars in sorted(bars_by_ticker.items()):
        if len(bars) < _MIN_BARS:
            raise ValueError(
                f"M3: {ticker} has {len(bars)} bars, need {_MIN_BARS} (run backfill-m3 first)"
            )
    return next(iter(dates))


def run_m3(
    engine,
    bars_by_ticker: dict[str, list[PriceBar]] | None = None,
    range: str = "6mo",  # noqa: A002
) -> dict:
    """Run M3 end to end.

    bars_by_ticker=None -> fetch all 12 tickers live (polite, ~seconds).
    Tests inject bars to stay offline. Backfill passes range="6mo"
    (same as the daily default now; kept as a param for the CLI).
    as_of always derives from the validated batch -- no caller override
    (red-team minor-5: override could desync freshness from stored rows).
    """
    if bars_by_ticker is None:
        bars_by_ticker = _fetch_all(range)
    as_of = _validate_batch(bars_by_ticker)  # fail-loud before any write
    momentum = sector_momentum(bars_by_ticker)

    session = SessionLocal(bind=engine)
    try:
        n_bars = PriceBarRepository(session).upsert_many(
            [b for bars in bars_by_ticker.values() for b in bars]
        )
        n_rows = SectorMomentumRepository(session).upsert_many(momentum)
        FreshnessRepository(session).mark("m3", as_of)
    finally:
        session.close()
    return {"as_of": as_of, "bars": n_bars, "sectors": n_rows}
