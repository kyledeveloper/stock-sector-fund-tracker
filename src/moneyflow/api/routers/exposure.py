"""M2 exposure endpoint. Thin: validate + forward to services."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from moneyflow.models import StockExposure
from moneyflow.services import exposure as exposure_service
from moneyflow.services.engine import get_engine

router = APIRouter()


def _engine():
    return get_engine()  # monkeypatched in tests


@router.get("/exposure", response_model=list[StockExposure])
def exposure(
    as_of: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[StockExposure]:
    """Top cross-sector exposures. as_of defaults to the latest stored day."""
    return exposure_service.top_exposures(_engine(), as_of=as_of, limit=limit)
