"""Daily pipeline CLI. One command per module; each is idempotent and
independently re-runnable. Invoked by systemd timer after 15:00 PDT."""

from __future__ import annotations

import typer

app = typer.Typer(help="US money-flow daily pipeline")


@app.command()
def m1() -> None:
    raise NotImplementedError("Phase 1: sector ETF flows")


@app.command()
def m2() -> None:
    raise NotImplementedError("Phase 2: implied exposure")


@app.command()
def m3() -> None:
    raise NotImplementedError("Phase 3: sector momentum")


@app.command()
def m4() -> None:
    raise NotImplementedError("Phase 4: smart money (EDGAR)")


@app.command()
def m5() -> None:
    raise NotImplementedError("Phase 5: options sentiment")


@app.command(name="run-all")
def run_all() -> None:
    for step in (m1, m2, m3, m4, m5):
        step()


if __name__ == "__main__":
    app()
