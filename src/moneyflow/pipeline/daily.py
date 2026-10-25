"""Daily pipeline CLI. One command per module; each is idempotent and
independently re-runnable. Invoked by systemd timer after 15:00 PDT.

M1 was cut from v1 (user decision 2026-10-01): no m1 command.
"""

from __future__ import annotations

import logging

import typer

from moneyflow.common.trading_day import calendar_warning, is_trading_day, today_et
from moneyflow.services import cboe as m5_service
from moneyflow.services import m2 as m2_service
from moneyflow.services import m3 as m3_service
from moneyflow.services import m4 as m4_service
from moneyflow.services.freshness import MODULES
from moneyflow.store.db import SessionLocal, get_engine
from moneyflow.store.migrate import apply_migrations
from moneyflow.store.repos import FreshnessRepository

app = typer.Typer(help="US money-flow daily pipeline")
logger = logging.getLogger(__name__)


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
    # Auditor P1 #4: each module is isolated. One module raising must not
    # cost the others their daily run; failures are collected and the CLI
    # exits non-zero so the timer/journal shows the run as failed.
    steps = (
        ("m2", m2_service.run_m2),
        ("m3", m3_service.run_m3),
        ("m4_13f", m4_service.run_13f),
        ("m4_form4", m4_service.run_form4),
        ("m5", m5_service.run_m5),
    )
    result: dict = {"skipped": False, "today": today, "errors": {}}
    for name, run in steps:
        try:
            result[name] = run(engine)
        except Exception as exc:  # noqa: BLE001 -- isolation boundary, re-reported below
            # Full traceback to stderr/journal; the summary keeps the one-liner.
            logger.exception("module %s failed", name)
            result[name] = None
            result["errors"][name] = f"{type(exc).__name__}: {exc}"
    return result


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


def _summarize(result: dict) -> list[str]:
    """One line per module; a failed module shows its error, never 'ok'."""
    errors = result["errors"]

    def m4_line() -> str:
        if "m4_13f" in errors or "m4_form4" in errors:
            parts = [f"{k} FAILED ({errors[k]})" for k in ("m4_13f", "m4_form4") if k in errors]
            return "m4 " + "; ".join(parts)
        r13, rf4 = result["m4_13f"], result["m4_form4"]
        # H2 (review 2026-10-02): "m4 ok" must not hide per-manager/per-filing errors.
        n = len(r13["errors"]) + len(rf4["errors"])
        note = f", {n} errors" if n else ""
        return (
            f"m4 ok (13f: {r13['checked']} checked / {r13['fetched']} new quarters; "
            f"form4: {rf4['fetched']} new filings, {rf4['buys']} buys{note})"
        )

    def m5_line() -> str:
        m5 = result["m5"]
        if m5["skipped"]:
            return f"m5 ok (skipped ({m5['reason']}))"
        return f"m5 ok (total {m5['total_put_call']} as of {m5['trade_date']})"

    lines = []
    for name, ok in (
        ("m2", lambda: f"m2 ok ({result['m2']['exposures']} exposures)"),
        ("m3", lambda: f"m3 ok ({result['m3']['sectors']} sectors)"),
    ):
        lines.append(f"{name} FAILED ({errors[name]})" if name in errors else ok())
    lines.append(m4_line())
    lines.append(f"m5 FAILED ({errors['m5']})" if "m5" in errors else m5_line())
    return lines


@app.command(name="run-all")
def run_all_cmd() -> None:
    result = run_all(_engine())
    warning = calendar_warning(result["today"])
    if warning:
        typer.echo(f"{result['today']}: CALENDAR WARNING: {warning}")
    if result["skipped"]:
        typer.echo(f"{result['today']}: not a trading day, writes skipped.")
        return
    for line in _summarize(result):
        typer.echo(f"{result['today']}: {line}")
    if result["errors"]:
        typer.echo(f"{result['today']}: {len(result['errors'])} module(s) FAILED")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
