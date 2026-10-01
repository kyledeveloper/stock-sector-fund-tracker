"""Daily pipeline CLI. One command per module; each is idempotent and
independently re-runnable. Invoked by systemd timer after 15:00 PDT.

M1 was cut from v1 (user decision 2026-10-01): no m1 command.
"""

from __future__ import annotations

import typer

from moneyflow.common.trading_day import is_trading_day, today_et
from moneyflow.services import m2 as m2_service
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
    return {"skipped": False, "today": today, "m2": m2_result}


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
    raise NotImplementedError("Phase 2: sector momentum (not built yet)")


@app.command()
def m4() -> None:
    raise NotImplementedError("Phase 3: smart money (not built yet)")


@app.command()
def m5() -> None:
    raise NotImplementedError("Phase 4: options sentiment (not built yet)")


@app.command(name="run-all")
def run_all_cmd() -> None:
    result = run_all()
    if result["skipped"]:
        typer.echo(f"{result['today']}: not a trading day, writes skipped.")
    else:
        typer.echo(f"{result['today']}: m2 ok ({result['m2']['exposures']} exposures).")


if __name__ == "__main__":
    app()
