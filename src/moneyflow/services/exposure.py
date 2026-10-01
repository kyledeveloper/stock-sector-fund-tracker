"""M2 read side: exposure queries for the API (thin layer)."""

from __future__ import annotations

from datetime import date

from moneyflow.models import StockExposure
from moneyflow.store.db import SessionLocal
from moneyflow.store.repos import ExposureRepository


def latest_as_of(engine) -> date | None:
    session = SessionLocal(bind=engine)
    try:
        return ExposureRepository(session).latest_as_of()
    finally:
        session.close()


def top_exposures(engine, as_of: date | None = None, limit: int = 50) -> list[StockExposure]:
    session = SessionLocal(bind=engine)
    try:
        repo = ExposureRepository(session)
        day = as_of or repo.latest_as_of()
        if day is None:
            return []
        return repo.top(day, limit)
    finally:
        session.close()
