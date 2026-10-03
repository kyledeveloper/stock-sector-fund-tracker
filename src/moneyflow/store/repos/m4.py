"""M4 repositories: 13F-HR holdings + Form 4 insider filings."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from moneyflow.models import Form4Filing, ThirteenFHolding

from ._common import _iso


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

    def filed_at_for(self, cik: str, report_date: date) -> date | None:
        """Newest filing date ingested for one quarter.

        Used for 13F-HR/A amendment detection: an amendment shares the
        quarter's report_date but has a newer filing_date.
        """
        row = self._s.execute(
            text(
                "SELECT MAX(filed_at) FROM thirteenf_holding WHERE cik = :cik AND report_date = :rd"
            ),
            {"cik": cik, "rd": _iso(report_date)},
        ).scalar()
        return date.fromisoformat(row) if row else None

    def delete_quarter(self, cik: str, report_date: date) -> int:
        """Delete one quarter's rows before an amendment replace.

        13F-HR/A restates the whole quarter: merge-by-upsert would leave
        removed positions behind forever, so the quarter is replaced,
        not merged. Does NOT commit -- the caller's following upsert_many
        commits the delete+insert atomically, so a failed upsert can never
        leave the quarter half-deleted. Returns rows deleted.
        """
        res = self._s.execute(
            text("DELETE FROM thirteenf_holding WHERE cik = :cik AND report_date = :rd"),
            {"cik": cik, "rd": _iso(report_date)},
        )
        return res.rowcount

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
