"""Freshness watchdog reads.

Phase 1: the Phase 0 stub is replaced with DB reads. staleness is
computed at read time from the T+1 rule in common/trading_day --
never stored, so the rule can't drift from the data.
"""

from __future__ import annotations

from datetime import date

from moneyflow.common.trading_day import is_stale
from moneyflow.models import Freshness
from moneyflow.store.db import SessionLocal
from moneyflow.store.repos import FreshnessRepository

MODULES = ("m2", "m3", "m4", "m5")


def get_freshness(engine, today: date) -> list[Freshness]:
    session = SessionLocal(bind=engine)
    try:
        stored = FreshnessRepository(session).all()
    finally:
        session.close()
    out: list[Freshness] = []
    for module in MODULES:
        rec = stored.get(module)
        as_of = rec[0] if rec else None
        kwargs: dict = {
            "module": module,
            "as_of": as_of,
            "stale": is_stale(as_of, today),
        }
        if rec and rec[1] is not None:
            kwargs["checked_at"] = rec[1]
        out.append(Freshness(**kwargs))
    return out
