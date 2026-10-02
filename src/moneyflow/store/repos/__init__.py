"""Repository pattern: the ONLY place SQL lives.

Each repository exposes typed methods over canonical models. Services and
routers never write SQL. If we outgrow SQLite, this package is the single
swap point for Postgres. One module per data domain; this __init__ re-exports
the public names so existing imports keep working.
"""

from moneyflow.store.repos.freshness import FreshnessRepository
from moneyflow.store.repos.m2 import ExposureRepository, HoldingRepository
from moneyflow.store.repos.m3 import PriceBarRepository, SectorMomentumRepository
from moneyflow.store.repos.m4 import Form4Repository, ThirteenFHoldingRepository

__all__ = [
    "ExposureRepository",
    "Form4Repository",
    "FreshnessRepository",
    "HoldingRepository",
    "PriceBarRepository",
    "SectorMomentumRepository",
    "ThirteenFHoldingRepository",
]
