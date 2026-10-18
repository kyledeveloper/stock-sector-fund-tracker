"""run_all isolates modules (Auditor P1 #4): one module raising must not stop
the rest, and the CLI must exit non-zero with a per-module summary."""

from __future__ import annotations

import pytest
from freezegun import freeze_time
from typer.testing import CliRunner

from moneyflow.pipeline import daily

OK = {
    "m2": {"exposures": 3, "holdings": 9, "as_of": "2026-10-13"},
    "m3": {"sectors": 11, "bars": 12, "as_of": "2026-10-13"},
    "m4_13f": {"checked": 12, "fetched": 0, "holdings": 0, "errors": []},
    "m4_form4": {"scanned": 5, "fetched": 1, "buys": 0, "errors": [], "volume_warning": False},
    "m5": {"skipped": True, "reason": "no data", "trade_date": "2026-10-13"},
}


@pytest.fixture()
def calls(monkeypatch):
    seen: list[str] = []

    def fake(name, boom=False):
        def run(engine, *a, **kw):
            seen.append(name)
            if boom:
                raise RuntimeError(f"{name} exploded")
            return OK[name]

        return run

    def install(failing: set[str]):
        monkeypatch.setattr(daily.m2_service, "run_m2", fake("m2", "m2" in failing))
        monkeypatch.setattr(daily.m3_service, "run_m3", fake("m3", "m3" in failing))
        monkeypatch.setattr(daily.m4_service, "run_13f", fake("m4_13f", "m4_13f" in failing))
        monkeypatch.setattr(daily.m4_service, "run_form4", fake("m4_form4", "m4_form4" in failing))
        monkeypatch.setattr(daily.m5_service, "run_m5", fake("m5", "m5" in failing))
        return seen

    return install


@freeze_time("2026-10-14 18:00:00")  # Wednesday, a trading day
def test_m2_failure_does_not_stop_other_modules(calls, tmp_path):
    from moneyflow.store.db import get_engine

    seen = calls({"m2"})
    result = daily.run_all(get_engine(tmp_path / "t.db"))
    assert seen == ["m2", "m3", "m4_13f", "m4_form4", "m5"]
    assert result["m2"] is None
    assert result["m3"] == OK["m3"]
    assert result["errors"] == {"m2": "RuntimeError: m2 exploded"}


@freeze_time("2026-10-14 18:00:00")
def test_all_ok_has_no_errors(calls, tmp_path):
    from moneyflow.store.db import get_engine

    calls(set())
    result = daily.run_all(get_engine(tmp_path / "t.db"))
    assert result["errors"] == {}


@freeze_time("2026-10-14 18:00:00")
def test_cli_exits_nonzero_and_reports_each_failed_module(calls, tmp_path, monkeypatch):
    from moneyflow.store.db import get_engine

    engine = get_engine(tmp_path / "t.db")
    monkeypatch.setattr(daily, "_engine", lambda: engine)
    calls({"m2", "m5"})
    res = CliRunner().invoke(daily.app, ["run-all"])
    assert res.exit_code == 1
    assert "m2 FAILED (RuntimeError: m2 exploded)" in res.output
    assert "m5 FAILED (RuntimeError: m5 exploded)" in res.output
    assert "m3 ok (11 sectors)" in res.output


@freeze_time("2026-10-14 18:00:00")
def test_cli_exits_zero_when_all_ok(calls, tmp_path, monkeypatch):
    from moneyflow.store.db import get_engine

    engine = get_engine(tmp_path / "t.db")
    monkeypatch.setattr(daily, "_engine", lambda: engine)
    calls(set())
    res = CliRunner().invoke(daily.app, ["run-all"])
    assert res.exit_code == 0, res.output
    assert "FAILED" not in res.output


@freeze_time("2028-11-15 18:00:00")  # inside the 90-day calendar warning window
def test_run_all_surfaces_calendar_warning(calls, tmp_path, monkeypatch):
    from moneyflow.store.db import get_engine

    engine = get_engine(tmp_path / "t.db")
    monkeypatch.setattr(daily, "_engine", lambda: engine)
    calls(set())
    res = CliRunner().invoke(daily.app, ["run-all"])
    assert res.exit_code == 0, res.output
    assert "CALENDAR WARNING" in res.output


@freeze_time("2026-10-14 18:00:00")
def test_module_failure_logs_traceback(calls, tmp_path, caplog):
    """Auditor P1 re-review #1: the journal must show where it broke."""
    from moneyflow.store.db import get_engine

    calls({"m3"})
    with caplog.at_level("ERROR", logger="moneyflow.pipeline.daily"):
        daily.run_all(get_engine(tmp_path / "t.db"))
    recs = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(recs) == 1
    assert "m3" in recs[0].getMessage()
    assert recs[0].exc_info is not None
    assert "Traceback" in caplog.text and "m3 exploded" in caplog.text
