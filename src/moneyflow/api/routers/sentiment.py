"""M5 sentiment endpoint: CBOE put/call series. Thin: validate + forward.

Language-neutral by contract: the response carries codes and numbers only,
never copy. The frontend maps values to zh/en text.
"""

from __future__ import annotations

from fastapi import APIRouter

from moneyflow.common.trading_day import is_stale, today_et
from moneyflow.services import cboe as m5_service
from moneyflow.services.engine import get_engine

router = APIRouter()


def _engine():
    return get_engine()  # monkeypatched in tests


@router.get("/sentiment/putcall")
def putcall(days: int = 90) -> dict:
    """CBOE daily put/call ratios (sentiment proxy, NOT a flow).

    days clamps to [1, 365] -- out of range clamps, never errors.
    stale follows the T+1 rule: data older than the last trading day
    before today grays out the panel.
    """
    rows = m5_service.putcall_series(_engine(), days)
    data = [
        {
            "date": r.trade_date.isoformat(),
            "total_put_call": r.total_put_call,
            "equity_put_call": r.equity_put_call,
        }
        for r in rows
    ]
    latest = rows[-1].trade_date if rows else None  # series is oldest-first
    return {
        "data": data,
        "as_of": latest.isoformat() if latest else None,
        "stale": is_stale(latest, today_et()),
    }
