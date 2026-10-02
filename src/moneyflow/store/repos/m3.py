"""M3 repositories: EOD price bars + sector momentum."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from moneyflow.models import PriceBar, SectorMomentum

from ._common import _iso


class PriceBarRepository:
    """M3 EOD bars (Yahoo chart, adjusted close). Phase 2."""

    def __init__(self, session) -> None:
        self._s = session

    def upsert_many(self, bars: list[PriceBar]) -> int:
        stmt = text(
            "INSERT INTO price_bar (as_of, ticker, close, volume)"
            " VALUES (:as_of, :ticker, :close, :volume)"
            " ON CONFLICT (as_of, ticker) DO UPDATE SET"
            " close=excluded.close, volume=excluded.volume"
        )
        self._s.execute(
            stmt,
            [
                {
                    "as_of": _iso(b.as_of),
                    "ticker": b.ticker,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ],
        )
        self._s.commit()
        return len(bars)


class SectorMomentumRepository:
    """M3 sector momentum snapshot. Phase 2."""

    def __init__(self, session) -> None:
        self._s = session

    def upsert_many(self, rows: list[SectorMomentum]) -> int:
        stmt = text(
            "INSERT INTO sector_momentum (as_of, ticker, rs_20d, rs_60d, rrg_quadrant)"
            " VALUES (:as_of, :ticker, :rs_20d, :rs_60d, :rrg_quadrant)"
            " ON CONFLICT (as_of, ticker) DO UPDATE SET"
            " rs_20d=excluded.rs_20d, rs_60d=excluded.rs_60d,"
            " rrg_quadrant=excluded.rrg_quadrant"
        )
        self._s.execute(
            stmt,
            [
                {
                    "as_of": _iso(r.as_of),
                    "ticker": r.ticker,
                    "rs_20d": r.rs_20d,
                    "rs_60d": r.rs_60d,
                    "rrg_quadrant": r.rrg_quadrant,
                }
                for r in rows
            ],
        )
        self._s.commit()
        return len(rows)

    def latest_as_of(self) -> date | None:
        row = self._s.execute(text("SELECT MAX(as_of) FROM sector_momentum")).scalar()
        return date.fromisoformat(row) if row else None

    def latest(self) -> list[SectorMomentum]:
        as_of = self.latest_as_of()
        if as_of is None:
            return []
        rows = self._s.execute(
            text(
                "SELECT as_of, ticker, rs_20d, rs_60d, rrg_quadrant"
                " FROM sector_momentum WHERE as_of = :as_of"
                " ORDER BY rs_20d DESC"
            ),
            {"as_of": _iso(as_of)},
        ).all()
        return [
            SectorMomentum(
                as_of=date.fromisoformat(r[0]),
                ticker=r[1],
                rs_20d=r[2],
                rs_60d=r[3],
                rrg_quadrant=r[4],
            )
            for r in rows
        ]
