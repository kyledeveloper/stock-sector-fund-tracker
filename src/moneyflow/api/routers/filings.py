"""M4 filings endpoints: 13F-HR manager positions + Form 4 insider buys.

Thin: validate + forward to services.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from moneyflow.models import InsiderBuyView, ManagerPositionsView
from moneyflow.services import m4 as m4_service
from moneyflow.services.engine import get_engine

router = APIRouter()


def _engine():
    return get_engine()  # monkeypatched in tests


@router.get("/filings/13f", response_model=list[ManagerPositionsView])
def thirteen_f(
    top_n: int = Query(default=15, ge=1, le=50),
) -> list[ManagerPositionsView]:
    """Latest 13F quarter per watchlist manager, top-N positions by value
    with quarter-over-quarter status. Empty list when M4 never ran."""
    return m4_service.latest_13f_views(_engine(), top_n=top_n)


@router.get("/filings/form4", response_model=list[InsiderBuyView])
def form4(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[InsiderBuyView]:
    """Recent officer/director open-market buys, newest first.
    Empty list when the Form 4 scan never ran."""
    return m4_service.recent_insider_buys(_engine(), limit=limit)
