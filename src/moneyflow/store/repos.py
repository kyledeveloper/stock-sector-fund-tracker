"""Repository pattern: the ONLY place SQL lives.

Each repository exposes typed methods over canonical models. Services and
routers never write SQL. If we outgrow SQLite, this module is the single
swap point for Postgres.
"""

from __future__ import annotations

from moneyflow.models import SectorFlow


class FlowRepository:
    """M1 sector flows. Phase 1 implements upsert/query."""

    def __init__(self, session) -> None:
        self._s = session

    def upsert_many(self, flows: list[SectorFlow]) -> int:
        raise NotImplementedError("Phase 1")

    def latest(self, limit: int = 11) -> list[SectorFlow]:
        raise NotImplementedError("Phase 1")
