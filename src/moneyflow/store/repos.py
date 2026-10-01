"""Repository pattern: the ONLY place SQL lives.

Each repository exposes typed methods over canonical models. Services and
routers never write SQL. If we outgrow SQLite, this module is the single
swap point for Postgres.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from sqlalchemy import text

from moneyflow.models import Holding, PriceBar, SectorMomentum, StockExposure


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


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


class FreshnessRepository:
    """Freshness watchdog table. Phase 1."""

    def __init__(self, session) -> None:
        self._s = session

    def mark(self, module: str, as_of: date | None) -> None:
        """Record a successful module run."""
        self._s.execute(
            text(
                "INSERT INTO freshness (module, as_of, checked_at)"
                " VALUES (:module, :as_of, :checked_at)"
                " ON CONFLICT (module) DO UPDATE SET"
                " as_of=excluded.as_of, checked_at=excluded.checked_at"
            ),
            {
                "module": module,
                "as_of": _iso(as_of),
                "checked_at": datetime.now(UTC).isoformat(),
            },
        )
        self._s.commit()

    def touch(self, module: str) -> None:
        """Bump checked_at without changing as_of (non-trading-day runs)."""
        self._s.execute(
            text(
                "INSERT INTO freshness (module, as_of, checked_at)"
                " VALUES (:module, NULL, :checked_at)"
                " ON CONFLICT (module) DO UPDATE SET checked_at=excluded.checked_at"
            ),
            {"module": module, "checked_at": datetime.now(UTC).isoformat()},
        )
        self._s.commit()

    def all(self) -> dict[str, tuple[date | None, datetime | None]]:
        rows = self._s.execute(text("SELECT module, as_of, checked_at FROM freshness")).all()
        out: dict[str, tuple[date | None, datetime | None]] = {}
        for module, as_of, checked_at in rows:
            out[module] = (
                date.fromisoformat(as_of) if as_of else None,
                datetime.fromisoformat(checked_at) if checked_at else None,
            )
        return out
