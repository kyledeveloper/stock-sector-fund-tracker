"""Cross-sector stock exposure snapshot (M2, v1 redefined 2026-10-01).

Pure functions only: canonical models in, canonical models out.
No I/O, no DB, no HTTP -- trivially unit-testable.

What this is: for each stock, the sum of its weights across the 11
sector ETFs (stocks can sit in several, e.g. GOOGL in XLC+XLY).
What this is NOT: a fund flow. Weight changes day-over-day are mostly
price moves. Never label it 主力/聪明钱/资金流入 -- the panel copy
contract test enforces the honest wording.
"""

from __future__ import annotations

from datetime import date

from moneyflow.models import Holding, StockExposure


def stock_exposure(holdings: list[Holding], as_of: date) -> list[StockExposure]:
    """Aggregate per-stock total weight across sector ETFs.

    Sorted by total_weight descending (rank-ready for the panel).
    """
    weights: dict[str, float] = {}
    etfs: dict[str, set[str]] = {}
    for h in holdings:
        weights[h.ticker] = weights.get(h.ticker, 0.0) + h.weight
        etfs.setdefault(h.ticker, set()).add(h.etf_ticker)
    exposures = [
        StockExposure(
            as_of=as_of,
            ticker=ticker,
            total_weight=w,
            etf_count=len(etfs[ticker]),
            contributing_etfs=sorted(etfs[ticker]),
        )
        for ticker, w in weights.items()
    ]
    exposures.sort(key=lambda e: e.total_weight, reverse=True)
    return exposures
