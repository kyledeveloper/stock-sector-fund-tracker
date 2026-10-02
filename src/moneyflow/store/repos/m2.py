"""M2 repositories: SSGA holdings + cross-sector stock exposure."""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text

from moneyflow.models import Holding, StockExposure

from ._common import _iso


class HoldingRepository:
    """M2 SSGA holdings. Phase 1."""

    def __init__(self, session) -> None:
        self._s = session

    def upsert_many(self, holdings: list[Holding]) -> int:
        stmt = text(
            "INSERT INTO holding (as_of, etf_ticker, ticker, name, weight)"
            " VALUES (:as_of, :etf_ticker, :ticker, :name, :weight)"
            " ON CONFLICT (as_of, etf_ticker, ticker) DO UPDATE SET"
            " name=excluded.name, weight=excluded.weight"
        )
        self._s.execute(
            stmt,
            [
                {
                    "as_of": _iso(h.as_of),
                    "etf_ticker": h.etf_ticker,
                    "ticker": h.ticker,
                    "name": h.name,
                    "weight": h.weight,
                }
                for h in holdings
            ],
        )
        self._s.commit()
        return len(holdings)


class ExposureRepository:
    """M2 cross-sector exposure snapshot. Phase 1."""

    def __init__(self, session) -> None:
        self._s = session

    def upsert_many(self, exposures: list[StockExposure]) -> int:
        stmt = text(
            "INSERT INTO stock_exposure (as_of, ticker, total_weight, etf_count, contributing)"
            " VALUES (:as_of, :ticker, :total_weight, :etf_count, :contributing)"
            " ON CONFLICT (as_of, ticker) DO UPDATE SET"
            " total_weight=excluded.total_weight, etf_count=excluded.etf_count,"
            " contributing=excluded.contributing"
        )
        self._s.execute(
            stmt,
            [
                {
                    "as_of": _iso(e.as_of),
                    "ticker": e.ticker,
                    "total_weight": e.total_weight,
                    "etf_count": e.etf_count,
                    "contributing": json.dumps(e.contributing_etfs),
                }
                for e in exposures
            ],
        )
        self._s.commit()
        return len(exposures)

    def latest_as_of(self) -> date | None:
        row = self._s.execute(text("SELECT MAX(as_of) FROM stock_exposure")).scalar()
        return date.fromisoformat(row) if row else None

    def top(self, as_of: date, limit: int) -> list[StockExposure]:
        rows = self._s.execute(
            text(
                "SELECT as_of, ticker, total_weight, etf_count, contributing"
                " FROM stock_exposure WHERE as_of = :as_of"
                " ORDER BY total_weight DESC LIMIT :limit"
            ),
            {"as_of": _iso(as_of), "limit": limit},
        ).all()
        return [
            StockExposure(
                as_of=date.fromisoformat(r[0]),
                ticker=r[1],
                total_weight=r[2],
                etf_count=r[3],
                contributing_etfs=json.loads(r[4]),
            )
            for r in rows
        ]
