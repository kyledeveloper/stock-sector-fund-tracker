"""Repository pattern: the ONLY place SQL lives.

Each repository exposes typed methods over canonical models. Services and
routers never write SQL. If we outgrow SQLite, this module is the single
swap point for Postgres.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from sqlalchemy import text

from moneyflow.models import (
    Form4Filing,
    Holding,
    PriceBar,
    SectorMomentum,
    StockExposure,
    ThirteenFHolding,
)


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


class ThirteenFHoldingRepository:
    """M4 13F-HR quarterly holdings (one row per position per quarter)."""

    def __init__(self, session) -> None:
        self._s = session

    def upsert_many(self, holdings: list[ThirteenFHolding]) -> int:
        stmt = text(
            "INSERT INTO thirteenf_holding (report_date, cik, cusip, put_call,"
            " filed_at, filer_name, issuer, title_of_class, value_usd, shares)"
            " VALUES (:report_date, :cik, :cusip, :put_call, :filed_at,"
            " :filer_name, :issuer, :title_of_class, :value_usd, :shares)"
            " ON CONFLICT (report_date, cik, cusip, put_call) DO UPDATE SET"
            " filed_at=excluded.filed_at, filer_name=excluded.filer_name,"
            " issuer=excluded.issuer, title_of_class=excluded.title_of_class,"
            " value_usd=excluded.value_usd, shares=excluded.shares"
        )
        self._s.execute(
            stmt,
            [
                {
                    "report_date": _iso(h.report_date),
                    "cik": h.cik,
                    "cusip": h.cusip,
                    "put_call": h.put_call,
                    "filed_at": _iso(h.filed_at),
                    "filer_name": h.filer_name,
                    "issuer": h.issuer,
                    "title_of_class": h.title_of_class,
                    "value_usd": h.value_usd,
                    "shares": h.shares,
                }
                for h in holdings
            ],
        )
        self._s.commit()
        return len(holdings)

    def report_dates(self, cik: str) -> list[date]:
        rows = self._s.execute(
            text(
                "SELECT DISTINCT report_date FROM thirteenf_holding"
                " WHERE cik = :cik ORDER BY report_date DESC"
            ),
            {"cik": cik},
        ).all()
        return [date.fromisoformat(r[0]) for r in rows]

    def for_quarter(self, cik: str, report_date: date) -> list[ThirteenFHolding]:
        rows = self._s.execute(
            text(
                "SELECT report_date, filed_at, cik, filer_name, issuer, cusip,"
                " title_of_class, value_usd, shares, put_call"
                " FROM thirteenf_holding WHERE cik = :cik AND report_date = :rd"
            ),
            {"cik": cik, "rd": _iso(report_date)},
        ).all()
        return [
            ThirteenFHolding(
                report_date=date.fromisoformat(r[0]),
                filed_at=date.fromisoformat(r[1]),
                cik=r[2],
                filer_name=r[3],
                issuer=r[4],
                cusip=r[5],
                title_of_class=r[6],
                value_usd=r[7],
                shares=r[8],
                put_call=r[9],
            )
            for r in rows
        ]

    def manager_quarters(self) -> list[tuple[str, str, date, date]]:
        """(cik, filer_name, report_date, filed_at) for each stored quarter."""
        rows = self._s.execute(
            text(
                "SELECT cik, MAX(filer_name), report_date, MAX(filed_at)"
                " FROM thirteenf_holding GROUP BY cik, report_date"
                " ORDER BY cik, report_date"
            )
        ).all()
        return [(r[0], r[1], date.fromisoformat(r[2]), date.fromisoformat(r[3])) for r in rows]


class Form4Repository:
    """M4 Form 4 insider filings + transactions (idempotent by accession)."""

    def __init__(self, session) -> None:
        self._s = session

    def upsert_filing(self, filing: Form4Filing) -> int:
        """Upsert one filing + its transactions. Returns the number of
        transaction rows actually inserted (B1: with the ordinal PK there
        are no silent drops; the service cross-checks this count)."""
        self._s.execute(
            text(
                "INSERT INTO form4_filing (accession_number, ticker, issuer,"
                " insider, officer_title, is_officer, is_director, filed_at,"
                " form_type, is_joint_filing)"
                " VALUES (:acc, :ticker, :issuer, :insider, :title,"
                " :officer, :director, :filed_at, :form_type, :joint)"
                " ON CONFLICT (accession_number) DO UPDATE SET"
                " ticker=excluded.ticker, issuer=excluded.issuer,"
                " insider=excluded.insider, officer_title=excluded.officer_title,"
                " is_officer=excluded.is_officer, is_director=excluded.is_director,"
                " filed_at=excluded.filed_at, form_type=excluded.form_type,"
                " is_joint_filing=excluded.is_joint_filing"
            ),
            {
                "acc": filing.accession_number,
                "ticker": filing.ticker,
                "issuer": filing.issuer,
                "insider": filing.insider,
                "title": filing.officer_title,
                "officer": int(filing.is_officer),
                "director": int(filing.is_director),
                "filed_at": _iso(filing.filed_at),
                "form_type": filing.form_type,
                "joint": int(filing.is_joint_filing),
            },
        )
        inserted = 0
        for t in filing.transactions:
            res = self._s.execute(
                text(
                    "INSERT INTO form4_transaction (accession_number, ordinal,"
                    " transaction_date, transaction_code, shares, price,"
                    " value_usd, side, is_open_market_buy, is_10b5_1)"
                    " VALUES (:acc, :ordinal, :tdate, :code, :shares, :price,"
                    " :value_usd, :side, :omb, :plan)"
                    " ON CONFLICT (accession_number, ordinal) DO NOTHING"
                ),
                {
                    "acc": filing.accession_number,
                    "ordinal": t.ordinal,
                    "tdate": _iso(t.transaction_date),
                    "code": t.transaction_code,
                    "shares": t.shares,
                    "price": t.price,
                    "value_usd": t.value_usd,
                    "side": t.side,
                    "omb": int(t.is_open_market_buy),
                    "plan": int(t.is_10b5_1),
                },
            )
            inserted += res.rowcount or 0
        self._s.commit()
        return inserted

    def has_accession(self, accession_number: str) -> bool:
        return (
            self._s.execute(
                text("SELECT 1 FROM form4_filing WHERE accession_number = :acc"),
                {"acc": accession_number},
            ).scalar()
            is not None
        )

    def recent_open_market_buys(self, limit: int = 50) -> list[dict]:
        """Officer/director open-market buys, newest first (the panel query)."""
        rows = self._s.execute(
            text(
                "SELECT f.ticker, f.issuer, f.insider, f.officer_title,"
                " f.filed_at, t.transaction_date, t.shares, t.price,"
                " t.value_usd, t.is_10b5_1, f.form_type, f.is_joint_filing"
                " FROM form4_transaction t JOIN form4_filing f"
                " ON f.accession_number = t.accession_number"
                " WHERE t.is_open_market_buy = 1"
                " AND (f.is_officer = 1 OR f.is_director = 1)"
                " ORDER BY t.transaction_date DESC, t.value_usd DESC"
                " LIMIT :limit"
            ),
            {"limit": limit},
        ).all()
        return [
            {
                "ticker": r[0],
                "issuer": r[1],
                "insider": r[2],
                "officer_title": r[3],
                "filed_at": r[4],
                "transaction_date": r[5],
                "shares": r[6],
                "price": r[7],
                "value_usd": r[8],
                "is_10b5_1": bool(r[9]),
                "is_amendment": (r[10] or "4") == "4/A",
                "is_joint_filing": bool(r[11]),
            }
            for r in rows
        ]


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
