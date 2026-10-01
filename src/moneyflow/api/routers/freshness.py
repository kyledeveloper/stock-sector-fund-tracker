"""Freshness watchdog endpoint.

Contract (locked in Phase 0, red-team B3): every frontend Panel consumes
GET /api/v1/freshness and renders "as of [ET]" or a stale gray-out from it.
The backend MUST keep serving this shape; the frontend MUST NOT invent
freshness state locally.

Phase 1: reads the freshness table; staleness follows the T+1 rule.
"""

from __future__ import annotations

from fastapi import APIRouter

from moneyflow.common.trading_day import today_et
from moneyflow.models import Freshness
from moneyflow.services.engine import get_engine
from moneyflow.services.freshness import get_freshness

router = APIRouter()


def _engine():
    return get_engine()  # monkeypatched in tests


@router.get("/freshness", response_model=list[Freshness])
def freshness() -> list[Freshness]:
    """Per-module freshness from the watchdog table."""
    return get_freshness(_engine(), today_et())
