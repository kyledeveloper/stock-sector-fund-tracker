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

from datetime import timedelta

from moneyflow.common.http import PoliteClient
from moneyflow.common.trading_day import today_et
from moneyflow.compute.filing_diff import diff_13f
from moneyflow.ingest.edgar import fetch_13f_holdings, peek_latest_13f
from moneyflow.ingest.edgar_form4 import fetch_form4_xml, parse_form4, search_form4
from moneyflow.models import M4_WATCHLIST, InsiderBuyView, ManagerPositionsView
from moneyflow.store.db import SessionLocal
from moneyflow.store.repos import (
    Form4Repository,
    FreshnessRepository,
    ThirteenFHoldingRepository,
)

TOP_N = 15
FORM4_WINDOW_DAYS = 3  # trailing window: covers the weekend gap on Mondays
FORM4_SOFT_WARN = 2000  # above: loud warning in stats, scan continues (M6)
FORM4_HARD_CAP = 10000  # above: fail loud, true upstream drift (M6)


def run_13f(engine, client: PoliteClient | None = None) -> dict:
    own = client is None
    client = client or PoliteClient()
    try:
        session = SessionLocal(bind=engine)
        try:
            repo = ThirteenFHoldingRepository(session)
            stats = {"checked": 0, "fetched": 0, "holdings": 0, "errors": []}
            for name, cik in M4_WATCHLIST:
                # M5: one manager's failure (e.g. a cover-only amendment that
                # even the fallback can't resolve) must not block the other 11.
                try:
                    cik10 = cik.zfill(10)
                    stored = repo.report_dates(cik10)
                    ref, _ = peek_latest_13f(cik, name, client)
                    stats["checked"] += 1
                    if stored and ref.report_date <= stored[0]:
                        continue  # already have this quarter (or newer)
                    holdings = fetch_13f_holdings(cik, name, client)
                    n = repo.upsert_many(holdings)
                    stats["fetched"] += 1
                    stats["holdings"] += n
                except Exception as e:  # noqa: BLE001 -- per-manager isolation
                    stats["errors"].append({"manager": name, "error": str(e)})
            # Freshness as_of = run date (pipeline health). The quarterly
            # truth (report/filed dates, ~45d lag) is labeled per manager
            # in the panel; marking report_date here would gray the panel
            # permanently under the T+1 staleness rule.
            FreshnessRepository(session).mark("m4", today_et())
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
                    # M4: without a previous quarter, every "new" badge means
                    # "first quarter on file" -- the panel says so explicitly.
                    has_previous_quarter=len(dates) > 1,
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


def run_form4(
    engine,
    client: PoliteClient | None = None,
    days: int = FORM4_WINDOW_DAYS,
    end=None,
) -> dict:
    """Daily Form 4 scan: EFTS search over the trailing window -> fetch each
    new filing's XML -> parse -> upsert (idempotent by accession).

    The trailing window (default 3 days) covers the weekend gap: Monday's
    run picks up Saturday/Sunday filings. Already-stored accessions are
    skipped BEFORE fetching XML, so steady-state cost is ~1 day of filings.

    M1: one poison filing (malformed XML, missing ticker, transient 403)
    no longer kills the whole market-wide scan -- it is recorded in
    stats["errors"] and the scan continues. Freshness is still marked:
    a partial scan with loud errors beats a silent 4-day blackout.
    M6: volume above FORM4_SOFT_WARN logs a loud warning but the scan
    continues; only above FORM4_HARD_CAP does it fail loud (true drift).
    """
    end = end or today_et()
    start = end - timedelta(days=days)
    own = client is None
    client = client or PoliteClient()
    try:
        hits = search_form4(start, end, client)
        if len(hits) > FORM4_HARD_CAP:
            raise ValueError(
                f"M4: EFTS returned {len(hits)} Form 4s for {start}..{end} "
                f"(hard cap {FORM4_HARD_CAP}) -- upstream drift, investigate"
            )
        session = SessionLocal(bind=engine)
        try:
            repo = Form4Repository(session)
            stats = {
                "scanned": len(hits),
                "fetched": 0,
                "buys": 0,
                "errors": [],
                "volume_warning": len(hits) > FORM4_SOFT_WARN,
                "window": f"{start}..{end}",
            }
            for h in hits:
                if repo.has_accession(h["adsh"]):
                    continue
                # M1: per-filing isolation.
                try:
                    xml = fetch_form4_xml(h["adsh"], h["ciks"], h["filename"], client)
                    filing = parse_form4(xml, accession_number=h["adsh"], form_type=h["form"])
                    inserted = repo.upsert_filing(filing)
                    assert inserted == len(filing.transactions), (
                        f"M4: {h['adsh']} parsed {len(filing.transactions)} txns "
                        f"but stored {inserted} (B1 regression)"
                    )
                except Exception as e:  # noqa: BLE001 -- per-filing isolation
                    stats["errors"].append({"adsh": h["adsh"], "error": str(e)})
                    continue
                stats["fetched"] += 1
                stats["buys"] += sum(
                    1
                    for t in filing.transactions
                    if t.is_open_market_buy and (filing.is_officer or filing.is_director)
                )
            FreshnessRepository(session).mark("m4", end)
            return stats
        finally:
            session.close()
    finally:
        if own:
            client.close()
