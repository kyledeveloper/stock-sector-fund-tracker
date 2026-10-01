"""M2 orchestration: SSGA holdings -> cross-sector exposure (thin layer).

No business logic here: fetch via adapters, validate the batch,
pure compute, store via repositories, mark freshness.
Idempotent by upsert; fail-loud on bad batches (red-team B1/B2).
"""

from __future__ import annotations

from datetime import date

from moneyflow.common.http import PoliteClient
from moneyflow.compute.exposure import stock_exposure
from moneyflow.ingest.ssga import SsgaAdapter
from moneyflow.models import SECTOR_ETFS, Holding
from moneyflow.store.db import SessionLocal
from moneyflow.store.repos import ExposureRepository, FreshnessRepository, HoldingRepository

# Data-quality gate (red-team B2): one ETF's weights must partition ~100%.
# Guards against upstream schema drift (e.g. SSGA flipping percent->fraction).
_WEIGHT_SUM_LOW, _WEIGHT_SUM_HIGH = 0.95, 1.05


def _fetch_all() -> list[Holding]:
    client = PoliteClient()
    try:
        out: list[Holding] = []
        for ticker in SECTOR_ETFS:
            out.extend(SsgaAdapter(ticker, client).fetch())
        return out
    finally:
        client.close()


def _validate_batch(holdings: list[Holding]) -> date:
    """Fail-loud batch validation; returns the single agreed as_of date.

    B1: all files must share one as_of. A lagging file merged under the
    majority date would silently corrupt the snapshot, so mixed dates
    raise instead of being "voted" away.
    B2: each ETF's weights must sum to ~1.0 (schema-drift guard).
    """
    by_etf: dict[str, list[Holding]] = {}
    for h in holdings:
        by_etf.setdefault(h.etf_ticker, []).append(h)
    dates = {h.as_of for h in holdings}
    if len(dates) > 1:
        divergent = ", ".join(
            f"{etf}={hs[0].as_of.isoformat()}" for etf, hs in sorted(by_etf.items())
        )
        raise ValueError(f"M2: mixed as_of dates across ETFs: {divergent}")
    for etf, hs in sorted(by_etf.items()):
        total = sum(h.weight for h in hs)
        if not _WEIGHT_SUM_LOW <= total <= _WEIGHT_SUM_HIGH:
            raise ValueError(
                f"M2: {etf} weights sum to {total:.4f}, expected ~1.0 "
                "(possible upstream schema drift)"
            )
    return next(iter(dates))


def run_m2(
    engine,
    holdings: list[Holding] | None = None,
    as_of: date | None = None,
) -> dict:
    """Run M2 end to end.

    holdings=None -> fetch all 11 ETFs live (polite, ~seconds).
    Tests inject holdings to stay offline.
    """
    if holdings is None:
        holdings = _fetch_all()
    if not holdings:
        raise ValueError("M2: no holdings to process")
    batch_as_of = _validate_batch(holdings)  # fail-loud before any write
    as_of = as_of or batch_as_of
    exposures = stock_exposure(holdings, as_of)

    session = SessionLocal(bind=engine)
    try:
        n_holdings = HoldingRepository(session).upsert_many(holdings)
        n_exposures = ExposureRepository(session).upsert_many(exposures)
        FreshnessRepository(session).mark("m2", as_of)
    finally:
        session.close()
    return {"as_of": as_of, "holdings": n_holdings, "exposures": n_exposures}
