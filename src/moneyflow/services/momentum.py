"""M3 read side: momentum queries for the API (thin layer)."""

from __future__ import annotations

from moneyflow.models import SectorMomentum
from moneyflow.store.db import SessionLocal
from moneyflow.store.repos import SectorMomentumRepository


def latest_momentum(engine) -> list[SectorMomentum]:
    session = SessionLocal(bind=engine)
    try:
        return SectorMomentumRepository(session).latest()
    finally:
        session.close()
