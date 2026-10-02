"""M5 repositories: CBOE daily put/call ratios (sentiment, not a flow)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import text

from moneyflow.models import CboeDaily

from ._common import _iso


class CboePutCallRepository:
    """M5 CBOE put/call rows, one per trade_date. Phase 4."""

    def __init__(self, session) -> None:
        self._s = session

    def upsert(self, day: CboeDaily) -> None:
        """Idempotent upsert (backfill re-runs overwrite the same row)."""
        self._s.execute(
            text(
                "INSERT INTO cboe_putcall"
                " (trade_date, total_put_call, equity_put_call, index_put_call,"
                " fetched_at, source_url)"
                " VALUES (:trade_date, :total_put_call, :equity_put_call,"
                " :index_put_call, :fetched_at, :source_url)"
                " ON CONFLICT (trade_date) DO UPDATE SET"
                " total_put_call=excluded.total_put_call,"
                " equity_put_call=excluded.equity_put_call,"
                " index_put_call=excluded.index_put_call,"
                " fetched_at=excluded.fetched_at, source_url=excluded.source_url"
            ),
            {
                "trade_date": _iso(day.trade_date),
                "total_put_call": day.total_put_call,
                "equity_put_call": day.equity_put_call,
                "index_put_call": day.index_put_call,
                "fetched_at": day.fetched_at.isoformat() if day.fetched_at else None,
                "source_url": day.source_url,
            },
        )
        self._s.commit()

    def series(self, days: int) -> list[CboeDaily]:
        """The trailing `days` rows, oldest first.

        LIMIT on ASC order would return the *oldest* days rows -- wrong
        once the table holds more rows than the window. The subquery
        picks the newest `days` dates first, then orders them oldest-first
        for the panel.
        """
        rows = self._s.execute(
            text(
                "SELECT trade_date, total_put_call, equity_put_call,"
                " index_put_call, fetched_at, source_url"
                " FROM cboe_putcall WHERE trade_date IN ("
                " SELECT trade_date FROM cboe_putcall"
                " ORDER BY trade_date DESC LIMIT :days)"
                " ORDER BY trade_date ASC"
            ),
            {"days": days},
        ).all()
        return [_row(r) for r in rows]

    def latest(self) -> CboeDaily | None:
        rows = self._s.execute(
            text(
                "SELECT trade_date, total_put_call, equity_put_call,"
                " index_put_call, fetched_at, source_url"
                " FROM cboe_putcall ORDER BY trade_date DESC LIMIT 1"
            )
        ).all()
        return _row(rows[0]) if rows else None


def _row(r) -> CboeDaily:
    return CboeDaily(
        trade_date=date.fromisoformat(r[0]),
        total_put_call=r[1],
        equity_put_call=r[2],
        index_put_call=r[3],
        fetched_at=datetime.fromisoformat(r[4]) if r[4] else None,
        source_url=r[5] or "",
    )
