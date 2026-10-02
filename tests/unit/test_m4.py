"""M4 13F service tests: new-quarter-only fetching, idempotent skip,
QoQ views, and the watchlist-wide failure mode. All offline via
MockTransport (this sandbox gets SEC 403; production runs on the VPS)."""

from __future__ import annotations

from pathlib import Path

import httpx
from sqlalchemy import create_engine

from moneyflow.common.http import PoliteClient
from moneyflow.models import M4_WATCHLIST
from moneyflow.services import m4 as m4_service
from moneyflow.store.migrate import apply_migrations

_FIXDIR = Path(__file__).parent.parent / "fixtures" / "edgar"
INFOTABLE = (_FIXDIR / "scion_infotable.xml").read_bytes()

BY_CIK = {cik.zfill(10): name for name, cik in M4_WATCHLIST}


def _good_handler(report_date: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "submissions/CIK" in url:
            cik10 = url.rsplit("CIK", 1)[1].split(".")[0]
            return httpx.Response(
                200,
                json={
                    "name": BY_CIK[cik10] + ", LLC",
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0000000000-26-000001"],
                            "filingDate": ["2026-08-14"],
                            "form": ["13F-HR"],
                            "reportDate": [report_date],
                        }
                    },
                },
            )
        if url.endswith("index.json"):
            return httpx.Response(
                200,
                json={
                    "directory": {"item": [{"name": "primary_doc.xml"}, {"name": "infotable.xml"}]}
                },
            )
        if url.endswith("infotable.xml"):
            return httpx.Response(200, content=INFOTABLE)
        return httpx.Response(404, text="not found")

    return handler


def _mock_client(report_date: str = "2026-06-30") -> PoliteClient:
    return PoliteClient(
        transport=httpx.MockTransport(_good_handler(report_date)),
        trust_env=False,
        min_interval_s=0,  # no pacing in tests; production uses 0.5s
    )


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/m4.db")
    apply_migrations(engine)
    return engine


def test_run_13f_fetches_all_managers_then_skips(tmp_path):
    engine = _engine(tmp_path)
    client = _mock_client()
    stats = m4_service.run_13f(engine, client=client)
    assert stats == {"checked": 12, "fetched": 12, "holdings": 12 * 8}
    # Second run: same quarter on file -> submissions checked, nothing fetched.
    stats2 = m4_service.run_13f(engine, client=client)
    assert stats2 == {"checked": 12, "fetched": 0, "holdings": 0}


def test_run_13f_new_quarter_refetches(tmp_path):
    engine = _engine(tmp_path)
    m4_service.run_13f(engine, client=_mock_client("2026-06-30"))
    stats = m4_service.run_13f(engine, client=_mock_client("2026-09-30"))
    assert stats["fetched"] == 12
    views = m4_service.latest_13f_views(engine)
    assert len(views) == 12
    scion = next(v for v in views if v.cik == "0001649339")
    assert str(scion.report_date) == "2026-09-30"
    # First quarter on record for the new report date -> all "new"... but
    # the manager HAS a prior quarter now, so diff runs against 2026-06-30.
    assert scion.new_count == 0  # same 8 cusips quarter-over-quarter
    assert all(p.status == "unchanged" for p in scion.positions)


def test_latest_13f_views_shape(tmp_path):
    engine = _engine(tmp_path)
    m4_service.run_13f(engine, client=_mock_client())
    views = m4_service.latest_13f_views(engine, top_n=3)
    assert len(views) == 12
    v = views[0]
    assert len(v.positions) == 3
    assert v.positions[0].value_usd >= v.positions[1].value_usd  # ranked
    assert v.new_count == 8  # first quarter: all 8 positions new (not just top-3)


def test_one_manager_failure_fails_loud(tmp_path):
    engine = _engine(tmp_path)

    good = _good_handler("2026-06-30")

    def bad_handler(request: httpx.Request) -> httpx.Response:
        if "CIK0001067983" in str(request.url):  # Berkshire 404s
            return httpx.Response(404, text="gone")
        return good(request)

    client = PoliteClient(
        transport=httpx.MockTransport(bad_handler), trust_env=False, min_interval_s=0
    )
    try:
        m4_service.run_13f(engine, client=client)
    except Exception:
        pass  # fail-loud, any exception type acceptable here
    else:  # pragma: no cover
        raise AssertionError("expected loud failure")


def test_watchlist_has_twelve_verified_managers():
    assert len(M4_WATCHLIST) == 12
    ciks = [c for _, c in M4_WATCHLIST]
    assert len(set(ciks)) == 12  # no duplicates
    assert all(c.isdigit() for c in ciks)
