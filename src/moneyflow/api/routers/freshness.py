"""Freshness watchdog endpoint.

Contract (locked in Phase 0, red-team B3): every frontend Panel consumes
GET /api/v1/freshness and renders "as of [ET]" or a stale gray-out from it.
The backend MUST keep serving this shape; the frontend MUST NOT invent
freshness state locally.

Phase 0 stub: no module has real data yet, so all four report stale.
Phase 1 replaces the body with a read of the freshness table.
"""

from __future__ import annotations

from fastapi import APIRouter

from moneyflow.models import Freshness

router = APIRouter()

# v1 modules: M1 cut per user decision 2026-10-01 (option D).
MODULES = ("m2", "m3", "m4", "m5")


@router.get("/freshness", response_model=list[Freshness])
def freshness() -> list[Freshness]:
    """Per-module freshness. Stub: everything stale until Phase 1."""
    return [Freshness(module=m, as_of=None, stale=True) for m in MODULES]
