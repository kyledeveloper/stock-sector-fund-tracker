"""Freshness watchdog repository: one row per module (m2..m5)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import text

from ._common import _iso


class FreshnessRepository:
    """Freshness watchdog: one row per module (m2..m5)."""

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
