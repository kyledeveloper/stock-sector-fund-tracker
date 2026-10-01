"""M3 momentum endpoint. Thin: validate + forward to services."""

from __future__ import annotations

from fastapi import APIRouter

from moneyflow.models import SectorMomentum
from moneyflow.services import momentum as momentum_service
from moneyflow.services.engine import get_engine

router = APIRouter()


def _engine():
    return get_engine()  # monkeypatched in tests


@router.get("/momentum", response_model=list[SectorMomentum])
def momentum() -> list[SectorMomentum]:
    """Latest sector momentum snapshot: 11 sectors ranked by 20d excess
    return vs SPY, with the simplified RRG quadrant. Empty list when
    M3 has never run."""
    return momentum_service.latest_momentum(_engine())
