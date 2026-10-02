"""M4 orchestration: 13F-HR quarterly holdings for the 12-manager watchlist.

13F is quarterly with ~45d lag, so the daily run is cheap: one submissions
JSON per manager (12 tiny requests); the full filing (index + XML) is only
fetched when a quarter newer than what's stored appears. One manager's
failure fails the whole run loud (same all-or-nothing standard as M2/M3) --
a partial manager set would silently bias the "smart money" picture.

Freshness note: module "m4" is shared with the Form 4 daily scan. as_of is
the newest data date across both sub-pipelines (usually the Form 4 date);
the 13F panel shows its own report/filed/lag labels per manager, which is
where quarterly-data honesty lives.
"""

from __future__ import annotations

from moneyflow.common.http import PoliteClient
from moneyflow.compute.filing_diff import diff_13f
from moneyflow.ingest.edgar import fetch_13f_holdings, peek_latest_13f
from moneyflow.models import M4_WATCHLIST, InsiderBuyView, ManagerPositionsView
from moneyflow.store.db import SessionLocal
from moneyflow.store.repos import (
    Form4Repository,
    FreshnessRepository,
    ThirteenFHoldingRepository,
)

TOP_N = 15


def run_13f(engine, client: PoliteClient | None = None) -> dict:
    own = client is None
    client = client or PoliteClient()
    try:
        session = SessionLocal(bind=engine)
        try:
            repo = ThirteenFHoldingRepository(session)
            stats = {"checked": 0, "fetched": 0, "holdings": 0}
            newest_report = None
            for name, cik in M4_WATCHLIST:
                cik10 = cik.zfill(10)
                stored = repo.report_dates(cik10)
                ref, _ = peek_latest_13f(cik, name, client)
                stats["checked"] += 1
                if stored:
                    newest_report = max(newest_report or stored[0], stored[0])
                    if ref.report_date <= stored[0]:
                        continue  # already have this quarter (or newer)
                holdings = fetch_13f_holdings(cik, name, client)
                n = repo.upsert_many(holdings)
                stats["fetched"] += 1
                stats["holdings"] += n
                newest_report = max(
                    newest_report or holdings[0].report_date, holdings[0].report_date
                )
            if newest_report is not None:
                FreshnessRepository(session).mark("m4", newest_report)
            return stats
        finally:
            session.close()
    finally:
        if own:
            client.close()


def latest_13f_views(engine, top_n: int = TOP_N) -> list[ManagerPositionsView]:
    """Latest quarter per manager with QoQ status (the panel query)."""
    session = SessionLocal(bind=engine)
    try:
        repo = ThirteenFHoldingRepository(session)
        out: list[ManagerPositionsView] = []
        for _name, cik in M4_WATCHLIST:
            cik10 = cik.zfill(10)
            dates = repo.report_dates(cik10)
            if not dates:
                continue
            cur = repo.for_quarter(cik10, dates[0])
            prev = repo.for_quarter(cik10, dates[1]) if len(dates) > 1 else []
            views = diff_13f(prev, cur)
            current = [v for v in views if v.status != "exited"]
            exited = [v for v in views if v.status == "exited"]
            if not cur:
                continue
            out.append(
                ManagerPositionsView(
                    cik=cik10,
                    filer_name=cur[0].filer_name,
                    report_date=dates[0],
                    filed_at=cur[0].filed_at,
                    positions=current[:top_n],
                    exited_count=len(exited),
                    new_count=sum(1 for v in current if v.status == "new"),
                )
            )
        return out
    finally:
        session.close()


def recent_insider_buys(engine, limit: int = 50) -> list[InsiderBuyView]:
    """Read side for the Form 4 panel (thin layer)."""
    session = SessionLocal(bind=engine)
    try:
        rows = Form4Repository(session).recent_open_market_buys(limit)
        return [InsiderBuyView(**r) for r in rows]
    finally:
        session.close()
