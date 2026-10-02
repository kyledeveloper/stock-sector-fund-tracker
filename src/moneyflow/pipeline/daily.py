"""Daily pipeline CLI. One command per module; each is idempotent and
independently re-runnable. Invoked by systemd timer after 15:00 PDT.

M1 was cut from v1 (user decision 2026-10-01): no m1 command.
"""

from __future__ import annotations

import typer

from moneyflow.common.trading_day import is_trading_day, today_et
from moneyflow.services import cboe as m5_service
from moneyflow.services import m2 as m2_service
from moneyflow.services import m3 as m3_service
from moneyflow.services import m4 as m4_service
from moneyflow.services.freshness import MODULES
from moneyflow.store.db import SessionLocal, get_engine
from moneyflow.store.migrate import apply_migrations
from moneyflow.store.repos import FreshnessRepository

app = typer.Typer(help="US money-flow daily pipeline")


def _engine():
    engine = get_engine()
    apply_migrations(engine)
    return engine


def run_all(engine=None) -> dict:
    """Daily run. On non-trading days only bumps checked_at (red-team M4):
    no writes, so Friday's data is never filed under Saturday's date."""
    engine = engine or _engine()
    apply_migrations(engine)
    today = today_et()
    if not is_trading_day(today):
        session = SessionLocal(bind=engine)
        try:
            repo = FreshnessRepository(session)
            for module in MODULES:
                repo.touch(module)
        finally:
            session.close()
        return {"skipped": True, "today": today}
    m2_result = m2_service.run_m2(engine)
    m3_result = m3_service.run_m3(engine)
    m4_13f_result = m4_service.run_13f(engine)
    m4_f4_result = m4_service.run_form4(engine)
    m5_result = m5_service.run_m5(engine)
    return {
        "skipped": False,
        "today": today,
        "m2": m2_result,
        "m3": m3_result,
        "m4_13f": m4_13f_result,
        "m4_form4": m4_f4_result,
        "m5": m5_result,
    }


@app.command()
def m2() -> None:
    """M2: SSGA holdings -> cross-sector exposure snapshot."""
    today = today_et()
    if not is_trading_day(today):
        typer.echo(f"{today}: not a trading day, m2 skipped (same gate as run-all).")
        return
    result = m2_service.run_m2(_engine())
    typer.echo(
        f"m2 done: {result['holdings']} holdings, "
        f"{result['exposures']} exposures as of {result['as_of']}"
    )


@app.command()
def m3() -> None:
    """M3: Yahoo EOD -> sector momentum vs SPY (simplified RRG)."""
    today = today_et()
    if not is_trading_day(today):
        typer.echo(f"{today}: not a trading day, m3 skipped (same gate as run-all).")
        return
    result = m3_service.run_m3(_engine())
    typer.echo(
        f"m3 done: {result['sectors']} sectors, "
        f"{result['bars']} bars stored as of {result['as_of']}"
    )


@app.command(name="backfill-m3")
def backfill_m3() -> None:
    """M3 backfill: fetch ~6 months of EOD for the 12 M3 tickers.

    One-off before the first daily run (60 trading days of history are
    required for the 60d window). Idempotent by upsert; safe to re-run.
    """
    result = m3_service.run_m3(_engine(), range="6mo")
    typer.echo(
        f"m3 backfill done: {result['sectors']} sectors, "
        f"{result['bars']} bars stored as of {result['as_of']}"
    )


@app.command()
def m4() -> None:
    """M4: EDGAR 13F-HR (12-manager watchlist, quarterly) + Form 4 scan.

    13F is quarterly: the daily run only re-fetches a manager when a new
    quarter appears (12 cheap submissions checks). Form 4 scans the
    trailing 3 days market-wide (covers the weekend gap on Mondays).
    """
    today = today_et()
    if not is_trading_day(today):
        typer.echo(f"{today}: not a trading day, m4 skipped (same gate as run-all).")
        return
    r13f = m4_service.run_13f(_engine())
    rf4 = m4_service.run_form4(_engine())
    typer.echo(
        f"m4 done: 13f {r13f['checked']} managers checked, "
        f"{r13f['fetched']} new quarters; "
        f"form4 {rf4['scanned']} filings scanned, {rf4['fetched']} new, "
        f"{rf4['buys']} insider buys."
    )
    for e in r13f["errors"]:
        typer.echo(f"  13F ERROR {e['manager']}: {e['error']}")
    for e in rf4["errors"]:
        typer.echo(f"  Form4 ERROR {e['adsh']}: {e['error']}")
    if rf4["volume_warning"]:
        typer.echo(
            f"  Form4 VOLUME WARNING: {rf4['scanned']} filings -- review whether"
            " this is a real volume spike or upstream drift."
        )


@app.command(name="backfill-m4")
def backfill_m4() -> None:
    """M4 backfill: full 13F-HR pull for all 12 watchlist managers +
    Form 4 scan over the trailing 7 days (one-off).

    Idempotent by upsert/accession; safe to re-run. The first stored 13F
    quarter shows all positions as "new"; the QoQ diff activates when the
    next quarter is filed.
    NOTE: live EDGAR pull -- needs non-403 egress (the user's VPS).
    """
    engine = _engine()
    r13f = m4_service.run_13f(engine)
    rf4 = m4_service.run_form4(engine, days=7)
    typer.echo(
        f"m4 backfill done: 13f {r13f['fetched']} managers, "
        f"{r13f['holdings']} holdings; form4 {rf4['fetched']} filings, "
        f"{rf4['buys']} insider buys."
    )


@app.command()
def m5() -> None:
    """M5: CBOE daily put/call ratio (sentiment proxy, not a flow)."""
    today = today_et()
    if not is_trading_day(today):
        typer.echo(f"{today}: not a trading day, m5 skipped (same gate as run-all).")
        return
    result = m5_service.run_m5(_engine())
    if result["skipped"]:
        typer.echo(f"m5 skipped: {result['reason']} (trade_date={result['trade_date']}).")
    else:
        typer.echo(
            f"m5 done: total {result['total_put_call']}, "
            f"equity {result['equity_put_call']}, "
            f"index {result['index_put_call']} "
            f"as of {result['trade_date']}"
        )


@app.command(name="backfill-m5")
def backfill_m5() -> None:
    """M5 backfill: trailing 90 calendar days of CBOE put/call ratios.

    Skips non-trading days before requesting; one request per day with a
    >=2s interval. Idempotent by upsert; safe to re-run. A single day's
    failure is recorded and the backfill continues.
    """
    result = m5_service.run_backfill_m5(_engine())
    typer.echo(
        f"m5 backfill done: {result['fetched']} fetched, "
        f"{result['skipped']} skipped, {len(result['errors'])} errors."
    )
    for e in result["errors"]:
        typer.echo(f"  ERROR {e['trade_date']}: {e['error']}")


@app.command(name="run-all")
def run_all_cmd() -> None:
    result = run_all()
    if result["skipped"]:
        typer.echo(f"{result['today']}: not a trading day, writes skipped.")
    else:
        m5 = result["m5"]
        m5_info = (
            f"skipped ({m5['reason']})"
            if m5["skipped"]
            else f"total {m5['total_put_call']} as of {m5['trade_date']}"
        )
        typer.echo(
            f"{result['today']}: m2 ok ({result['m2']['exposures']} exposures), "
            f"m3 ok ({result['m3']['sectors']} sectors), "
            f"m4 ok (13f: {result['m4_13f']['checked']} checked / "
            f"{result['m4_13f']['fetched']} new quarters; "
            f"form4: {result['m4_form4']['fetched']} new filings, "
            f"{result['m4_form4']['buys']} buys), "
            f"m5 ok ({m5_info})."
        )


if __name__ == "__main__":
    app()
