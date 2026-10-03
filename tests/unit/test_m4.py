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
    assert stats["checked"] == 12 and stats["fetched"] == 12
    assert stats["holdings"] == 12 * 8 and stats["errors"] == []
    # Second run: same quarter on file -> submissions checked, nothing fetched.
    stats2 = m4_service.run_13f(engine, client=client)
    assert stats2["checked"] == 12 and stats2["fetched"] == 0 and stats2["errors"] == []


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
    assert scion.has_previous_quarter is True  # M4: no first-quarter caveat


def test_first_quarter_flagged_for_honest_badges(tmp_path):
    """M4: with only one quarter on file, has_previous_quarter is False --
    the panel must caveat that 'new' badges mean 'first quarter on file'."""
    engine = _engine(tmp_path)
    m4_service.run_13f(engine, client=_mock_client())
    views = m4_service.latest_13f_views(engine)
    assert len(views) == 12
    assert all(v.has_previous_quarter is False for v in views)


def test_latest_13f_views_shape(tmp_path):
    engine = _engine(tmp_path)
    m4_service.run_13f(engine, client=_mock_client())
    views = m4_service.latest_13f_views(engine, top_n=3)
    assert len(views) == 12
    v = views[0]
    assert len(v.positions) == 3
    assert v.positions[0].value_usd >= v.positions[1].value_usd  # ranked
    assert v.new_count == 8  # first quarter: all 8 positions new (not just top-3)


def test_one_manager_failure_isolated(tmp_path):
    """M5: one manager's loud failure no longer blocks the other 11 --
    it is recorded in stats["errors"] and the run continues."""
    engine = _engine(tmp_path)

    good = _good_handler("2026-06-30")

    def bad_handler(request: httpx.Request) -> httpx.Response:
        if "CIK0001067983" in str(request.url):  # Berkshire 404s
            return httpx.Response(404, text="gone")
        return good(request)

    client = PoliteClient(
        transport=httpx.MockTransport(bad_handler), trust_env=False, min_interval_s=0
    )
    stats = m4_service.run_13f(engine, client=client)
    assert stats["fetched"] == 11
    assert len(stats["errors"]) == 1
    assert "Berkshire" in stats["errors"][0]["manager"]
    # The other 11 managers' data is intact.
    assert len(m4_service.latest_13f_views(engine)) == 11


def test_total_13f_outage_does_not_mark_fresh(tmp_path):
    """Total SEC outage (every CIK 403) must not paint m4 as_of=today.

    Live failure mode on blocked egress: checked==0, empty panels, but the
    old code still marked freshness fresh -- empty 13F/Form4 looked healthy.
    """
    from moneyflow.common.trading_day import today_et
    from moneyflow.store.db import SessionLocal
    from moneyflow.store.repos import FreshnessRepository

    engine = _engine(tmp_path)

    def all_403(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    client = PoliteClient(transport=httpx.MockTransport(all_403), trust_env=False, min_interval_s=0)
    stats = m4_service.run_13f(engine, client=client)
    assert stats["checked"] == 0 and stats["fetched"] == 0
    assert len(stats["errors"]) == 12
    assert m4_service.latest_13f_views(engine) == []
    session = SessionLocal(bind=engine)
    try:
        rec = FreshnessRepository(session).all().get("m4")
    finally:
        session.close()
    assert rec is not None
    as_of, checked_at = rec
    assert as_of is None  # touch(), not mark(today)
    assert checked_at is not None
    # And a later successful run still marks normally.
    ok = m4_service.run_13f(engine, client=_mock_client())
    assert ok["checked"] == 12 and ok["fetched"] == 12
    session = SessionLocal(bind=engine)
    try:
        rec2 = FreshnessRepository(session).all()["m4"]
    finally:
        session.close()
    assert rec2[0] == today_et()


def test_watchlist_has_twelve_verified_managers():
    assert len(M4_WATCHLIST) == 12
    ciks = [c for _, c in M4_WATCHLIST]
    assert len(set(ciks)) == 12  # no duplicates
    assert all(c.isdigit() for c in ciks)


# --- Form 4 daily scan (MockTransport) ---

from moneyflow.services import m4 as m4_scan  # noqa: E402  (same module, alias for clarity)

_SAMSARA = (_FIXDIR / "form4_samsara.xml").read_bytes()

_BUY_FILING_XML = b"""<ownershipDocument><issuer><issuerTradingSymbol>XYZ</issuerTradingSymbol>
<issuerName>Xyz Inc.</issuerName><issuerCik>0000000001</issuerCik></issuer>
<reportingOwner><reportingOwnerId><rptOwnerCik>0000000002</rptOwnerCik>
<rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId><reportingOwnerRelationship>
<isDirector>true</isDirector><isOfficer>true</isOfficer><officerTitle>CFO</officerTitle>
<isTenPercentOwner>false</isTenPercentOwner><isOther>false</isOther>
</reportingOwnerRelationship></reportingOwner>
<nonDerivativeTable><nonDerivativeTransaction>
<transactionDate><value>2026-09-28</value></transactionDate>
<transactionCoding><transactionFormType>4</transactionFormType>
<transactionCode>P</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>1000</value></transactionShares>
<transactionPricePerShare><value>50.5</value></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
</transactionAmounts></nonDerivativeTransaction></nonDerivativeTable>
<ownerSignature><signatureDate>2026-09-29</signatureDate></ownerSignature>
</ownershipDocument>"""


def _efts_hits(adshs, forms=None):
    forms = forms or {}
    return {
        "hits": {
            "total": {"value": len(adshs)},
            "hits": [
                {
                    "_id": f"{a}:ownership.xml",
                    "_source": {
                        "adsh": a,
                        "ciks": ["0000000001", "0000000002"],
                        "file_date": "2026-10-01",
                        "form": forms.get(a, "4"),
                    },
                }
                for a in adshs
            ],
        }
    }


def _form4_client(
    xml_by_adsh: dict, efts_adshs: list, forms=None, default_xml: bytes | None = None
) -> PoliteClient:
    """Mock honors the EFTS `from` param (M7: the old mock ignored it, so the
    pagination loop was only ever exercised on a single page)."""
    calls = {"efts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "efts.sec.gov" in url:
            calls["efts"] += 1
            offset = int(request.url.params.get("from", 0))
            size = int(request.url.params.get("size", 100))
            hits = _efts_hits(efts_adshs, forms)["hits"]["hits"][offset : offset + size]
            return httpx.Response(
                200, json={"hits": {"total": {"value": len(efts_adshs)}, "hits": hits}}
            )
        if "/Archives/edgar/data/" in url:
            # first CIK 404s -> exercises the CIK fallback
            if "/0000000001/" in url:
                return httpx.Response(404, text="nope")
            for adsh, xml in xml_by_adsh.items():
                if adsh.replace("-", "") in url:
                    return httpx.Response(200, content=xml)
            if default_xml is not None:
                return httpx.Response(200, content=default_xml)
            return httpx.Response(404, text="nope")
        return httpx.Response(404, text="not found")

    client = PoliteClient(transport=httpx.MockTransport(handler), trust_env=False, min_interval_s=0)
    client._efts_calls = calls  # test introspection
    return client


def test_run_form4_stores_and_skips(tmp_path):
    from datetime import date

    engine = _engine(tmp_path)
    client = _form4_client({"0001895111-26-000019": _SAMSARA}, ["0001895111-26-000019"])
    stats = m4_scan.run_form4(engine, client=client, end=date(2026, 10, 1))
    assert stats["scanned"] == 1 and stats["fetched"] == 1 and stats["buys"] == 0
    # Re-run: accession already stored -> XML not re-fetched.
    stats2 = m4_scan.run_form4(engine, client=client, end=date(2026, 10, 1))
    assert stats2["fetched"] == 0


def test_run_form4_counts_buys_and_read_side(tmp_path):
    from datetime import date

    engine = _engine(tmp_path)
    client = _form4_client({"0000000002-26-000001": _BUY_FILING_XML}, ["0000000002-26-000001"])
    stats = m4_scan.run_form4(engine, client=client, end=date(2026, 10, 1))
    assert stats["buys"] == 1
    buys = m4_scan.recent_insider_buys(engine)
    assert len(buys) == 1
    b = buys[0]
    assert b.ticker == "XYZ" and b.insider == "Jane Doe"
    assert b.value_usd == 1000 * 50.5
    assert b.officer_title == "CFO"


def test_run_form4_volume_soft_warn_and_hard_cap(tmp_path):
    """M6: above the soft warn the scan continues with a loud flag; only
    above the hard cap does it fail loud (true upstream drift)."""
    from datetime import date

    engine = _engine(tmp_path)
    adshs = [f"0000000001-26-{i:06d}" for i in range(2001)]
    client = _form4_client({}, adshs, default_xml=_BUY_FILING_XML)
    stats = m4_scan.run_form4(engine, client=client, end=date(2026, 10, 1))
    assert stats["volume_warning"] is True
    assert stats["fetched"] == 2001  # scan continued, nothing lost

    engine2_dir = tmp_path / "two"
    engine2_dir.mkdir(exist_ok=True)
    engine2 = _engine(engine2_dir)
    adshs2 = [f"0000000001-26-{i:06d}" for i in range(10001)]
    client2 = _form4_client({}, adshs2, default_xml=_BUY_FILING_XML)
    try:
        m4_scan.run_form4(engine2, client=client2, end=date(2026, 10, 1))
    except ValueError as e:
        assert "hard cap" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_fetch_form4_xml_all_ciks_404(tmp_path):
    from moneyflow.ingest.edgar_form4 import fetch_form4_xml

    client = _form4_client({}, [])
    try:
        fetch_form4_xml("0000000001-26-000001", ["0000000001"], "ownership.xml", client)
    except ValueError as e:
        assert "not found" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


# --- Red-team regression tests (Phase 3 red team, 2026-10-02) ---


def _txn_row(code="P", ad="A", shares=1000, price=50.0, date="2026-09-28"):
    return f"""<nonDerivativeTransaction>
<transactionDate><value>{date}</value></transactionDate>
<transactionCoding><transactionFormType>4</transactionFormType>
<transactionCode>{code}</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>{shares}</value></transactionShares>
<transactionPricePerShare><value>{price}</value></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode>
</transactionAmounts></nonDerivativeTransaction>"""


def _filing_xml(rows, owners=None, footnotes=""):
    owners = owners or [
        ("0000000002", "Jane Doe", "true", "true", "CFO", "false"),
    ]
    owner_xml = "".join(
        f"""<reportingOwner><reportingOwnerId><rptOwnerCik>{cik}</rptOwnerCik>
<rptOwnerName>{name}</rptOwnerName></reportingOwnerId><reportingOwnerRelationship>
<isDirector>{d}</isDirector><isOfficer>{o}</isOfficer><officerTitle>{t}</officerTitle>
<isTenPercentOwner>{ten}</isTenPercentOwner><isOther>false</isOther>
</reportingOwnerRelationship></reportingOwner>"""
        for cik, name, d, o, t, ten in owners
    )
    return (
        """<ownershipDocument><issuer><issuerTradingSymbol>XYZ</issuerTradingSymbol>
<issuerName>Xyz Inc.</issuerName><issuerCik>0000000001</issuerCik></issuer>"""
        + owner_xml
        + "<nonDerivativeTable>"
        + "".join(rows)
        + "</nonDerivativeTable>"
        + footnotes
        + """<ownerSignature><signatureDate>2026-09-29</signatureDate></ownerSignature>
</ownershipDocument>"""
    ).encode()


def test_b1_two_lots_same_shares_both_stored(tmp_path):
    """B1: two 500-share P/A lots at different prices in one filing --
    the old PK silently dropped the second; both must survive now."""
    from datetime import date

    xml = _filing_xml([_txn_row(shares=500, price=50.10), _txn_row(shares=500, price=50.25)])
    engine = _engine(tmp_path)
    client = _form4_client({"0000000003-26-000001": xml}, ["0000000003-26-000001"])
    stats = m4_scan.run_form4(engine, client=client, end=date(2026, 10, 1))
    assert stats["buys"] == 2
    buys = m4_scan.recent_insider_buys(engine)
    assert len(buys) == 2
    assert sorted(b.price for b in buys) == [50.10, 50.25]
    assert sum(b.value_usd for b in buys) == 500 * 50.10 + 500 * 50.25


def test_m1_poison_filing_does_not_kill_scan(tmp_path):
    """M1: a malformed filing mid-list is recorded and skipped; the rest
    of the scan completes and freshness is still marked."""
    from datetime import date

    from moneyflow.store.db import SessionLocal
    from moneyflow.store.repos import FreshnessRepository

    adshs = ["0000000004-26-000001", "0000000004-26-000002", "0000000004-26-000003"]
    xml_by = {
        adshs[0]: _BUY_FILING_XML,
        adshs[1]: b"<ownershipDocument><broken",
        adshs[2]: _BUY_FILING_XML,
    }
    engine = _engine(tmp_path)
    client = _form4_client(xml_by, adshs)
    stats = m4_scan.run_form4(engine, client=client, end=date(2026, 10, 1))
    assert stats["fetched"] == 2
    assert len(stats["errors"]) == 1
    assert stats["errors"][0]["adsh"] == adshs[1]
    session = SessionLocal(bind=engine)
    try:
        rec = FreshnessRepository(session).all()["m4"]
    finally:
        session.close()
    assert str(rec[0]) == "2026-10-01"  # freshness marked despite the error


def test_m2_amendment_flagged_not_double_counted_silently(tmp_path):
    """M2: a 4/A filing is flagged in the view (v1 does not auto-supersede,
    but the amendment is visible, not silently double-counted)."""
    from datetime import date

    adsh = "0000000005-26-000001"
    engine = _engine(tmp_path)
    client = _form4_client({adsh: _BUY_FILING_XML}, [adsh], forms={adsh: "4/A"})
    m4_scan.run_form4(engine, client=client, end=date(2026, 10, 1))
    buys = m4_scan.recent_insider_buys(engine)
    assert len(buys) == 1
    assert buys[0].is_amendment is True


def test_m3_joint_filers_no_silent_exclusion(tmp_path):
    """M3: joint filing where the FIRST owner is a non-officer trust and the
    second is the CFO -- the old code attributed to the trust and dropped
    the buy from the officer/director filter entirely."""
    from datetime import date

    from moneyflow.ingest.edgar_form4 import parse_form4

    xml = _filing_xml(
        [_txn_row()],
        owners=[
            ("0000000003", "John Smith Revocable Trust", "false", "false", "", "true"),
            ("0000000004", "Jane Smith", "true", "true", "CFO", "false"),
        ],
    )
    filing = parse_form4(xml, accession_number="x")
    assert filing.is_joint_filing is True
    assert "Jane Smith" in filing.insider and "John Smith Revocable Trust" in filing.insider
    assert filing.is_officer is True and filing.is_director is True

    engine = _engine(tmp_path)
    adsh = "0000000006-26-000001"
    client = _form4_client({adsh: xml}, [adsh])
    stats = m4_scan.run_form4(engine, client=client, end=date(2026, 10, 1))
    assert stats["buys"] == 1  # not silently excluded
    buys = m4_scan.recent_insider_buys(engine)
    assert len(buys) == 1 and buys[0].is_joint_filing is True


def test_m7_search_form4_paginates_and_missing_total_fails_loud(tmp_path):
    """M7: the mock now honors `from`, so pagination is really exercised;
    a missing hits.total fails loud instead of silently truncating."""
    from datetime import date

    from moneyflow.ingest.edgar_form4 import search_form4

    adshs = [f"0000000007-26-{i:06d}" for i in range(250)]
    client = _form4_client({}, adshs, default_xml=_BUY_FILING_XML)
    hits = search_form4(date(2026, 9, 28), date(2026, 10, 1), client)
    assert len(hits) == 250
    assert client._efts_calls["efts"] == 3  # 100 + 100 + 50

    def no_total_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hits": {"hits": []}})

    bad = PoliteClient(
        transport=httpx.MockTransport(no_total_handler), trust_env=False, min_interval_s=0
    )
    try:
        search_form4(date(2026, 9, 28), date(2026, 10, 1), bad)
    except ValueError as e:
        assert "hits.total" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_10b5_1_negation_not_flagged():
    """MINOR-7: 'NOT pursuant to a 10b5-1 plan' must not flag the trade."""
    from moneyflow.ingest.edgar_form4 import parse_form4

    footnotes = (
        "<footnotes><footnote id='F1'>This transaction was NOT pursuant to "
        "a 10b5-1 trading plan.</footnote></footnotes>"
    )
    xml = _filing_xml([_txn_row()], footnotes=footnotes).replace(
        b"<nonDerivativeTransaction>",
        b"<nonDerivativeTransaction><footnoteId id='F1'/>",
        1,
    )
    filing = parse_form4(xml)
    assert filing.transactions[0].is_10b5_1 is False

    yes = (
        _filing_xml([_txn_row()])
        .replace(
            b"</nonDerivativeTable>",
            b"</nonDerivativeTable><footnotes><footnote id='F1'>"
            b"Pursuant to a 10b5-1 trading plan.</footnote></footnotes>",
        )
        .replace(
            b"<nonDerivativeTransaction>",
            b"<nonDerivativeTransaction><footnoteId id='F1'/>",
            1,
        )
    )
    assert parse_form4(yes).transactions[0].is_10b5_1 is True


# ---------------------------------------------------------------------------
# H1 (review 2026-10-02): 13F-HR/A amendments must be adopted.
# A same-quarter amendment shares the report_date but has a newer
# filing_date. The old report_date-only skip dropped it forever, and
# merge-by-upsert would have left removed positions behind.
# ---------------------------------------------------------------------------


def _infotable_xml(rows: list[tuple[str, str, int, int]]) -> bytes:
    """Minimal 13F info table. rows: (issuer, cusip, value_usd, shares)."""
    body = "".join(
        "<infoTable>"
        f"<nameOfIssuer>{issuer}</nameOfIssuer>"
        "<titleOfClass>COM</titleOfClass>"
        f"<cusip>{cusip}</cusip>"
        f"<value>{value}</value>"
        "<shrsOrPrnAmt>"
        f"<sshPrnamt>{shares}</sshPrnamt>"
        "<sshPrnamtType>SH</sshPrnamtType>"
        "</shrsOrPrnAmt>"
        "</infoTable>"
        for issuer, cusip, value, shares in rows
    )
    return f"<informationTable>{body}</informationTable>".encode()


def _mock_client_for(report_date: str, filing_date: str, form: str, xml: bytes) -> PoliteClient:
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
                            "accessionNumber": ["0000000000-26-000009"],
                            "filingDate": [filing_date],
                            "form": [form],
                            "reportDate": [report_date],
                        }
                    },
                },
            )
        if url.endswith("index.json"):
            return httpx.Response(
                200,
                json={
                    "directory": {
                        "item": [
                            {"name": "primary_doc.xml"},
                            {"name": "infotable.xml"},
                        ]
                    }
                },
            )
        if url.endswith("infotable.xml"):
            return httpx.Response(200, content=xml)
        return httpx.Response(404, text="not found")

    return PoliteClient(transport=httpx.MockTransport(handler), trust_env=False, min_interval_s=0)


def _quarter_cusips(engine, cik10: str, report_date: str) -> dict[str, int]:
    from moneyflow.store.db import SessionLocal
    from moneyflow.store.repos import ThirteenFHoldingRepository

    session = SessionLocal(bind=engine)
    try:
        from datetime import date as _date

        rows = ThirteenFHoldingRepository(session).for_quarter(
            cik10, _date.fromisoformat(report_date)
        )
        return {r.cusip: r.value_usd for r in rows}
    finally:
        session.close()


def test_run_13f_amendment_same_quarter_replaces(tmp_path):
    """H1: a 13F-HR/A filed after ingest replaces the quarter.

    Base: AAA + BBB. Amendment: BBB restated, CCC added, AAA removed.
    After the amendment run the quarter must be exactly {BBB, CCC} --
    AAA must not linger (no merge-by-upsert).
    """
    engine = _engine(tmp_path)
    base = _infotable_xml(
        [("AAA CORP", "111111111", 1000, 10), ("BBB CORP", "222222222", 2000, 20)]
    )
    amend = _infotable_xml(
        [("BBB CORP", "222222222", 9999, 99), ("CCC CORP", "333333333", 3000, 30)]
    )
    s1 = m4_service.run_13f(
        engine, client=_mock_client_for("2026-03-31", "2026-05-15", "13F-HR", base)
    )
    assert s1["fetched"] == 12 and s1["errors"] == []

    s2 = m4_service.run_13f(
        engine, client=_mock_client_for("2026-03-31", "2026-08-20", "13F-HR/A", amend)
    )
    assert s2["fetched"] == 12, "amendment must be adopted, not skipped"
    assert s2["errors"] == []

    cusips = _quarter_cusips(engine, "0001649339", "2026-03-31")
    assert set(cusips) == {"222222222", "333333333"}, "AAA must be deleted"
    assert cusips["222222222"] == 9999, "BBB must carry the amended value"


def test_run_13f_same_filing_not_refetched(tmp_path):
    """H1: same report_date AND same filing_date -> skip (no churn)."""
    engine = _engine(tmp_path)
    base = _infotable_xml([("AAA CORP", "111111111", 1000, 10)])
    m4_service.run_13f(engine, client=_mock_client_for("2026-03-31", "2026-05-15", "13F-HR", base))
    s2 = m4_service.run_13f(
        engine, client=_mock_client_for("2026-03-31", "2026-05-15", "13F-HR", base)
    )
    assert s2["fetched"] == 0 and s2["errors"] == []


def test_run_13f_failed_amendment_fetch_keeps_old_quarter(tmp_path):
    """H1: fetch-before-delete -- a failed amendment fetch must not wipe
    the good quarter we already have."""
    engine = _engine(tmp_path)
    base = _infotable_xml([("AAA CORP", "111111111", 1000, 10)])
    m4_service.run_13f(engine, client=_mock_client_for("2026-03-31", "2026-05-15", "13F-HR", base))

    def bad_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "submissions/CIK" in url:
            cik10 = url.rsplit("CIK", 1)[1].split(".")[0]
            return httpx.Response(
                200,
                json={
                    "name": BY_CIK[cik10] + ", LLC",
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0000000000-26-000009"],
                            "filingDate": ["2026-08-20"],
                            "form": ["13F-HR/A"],
                            "reportDate": ["2026-03-31"],
                        }
                    },
                },
            )
        return httpx.Response(404, text="gone")  # index.json 404s -> fetch fails

    client = PoliteClient(
        transport=httpx.MockTransport(bad_handler), trust_env=False, min_interval_s=0
    )
    s2 = m4_service.run_13f(engine, client=client)
    assert s2["fetched"] == 0 and len(s2["errors"]) == 12
    # old quarter intact
    assert set(_quarter_cusips(engine, "0001649339", "2026-03-31")) == {"111111111"}


# ---------------------------------------------------------------------------
# M1 (review 2026-10-02): fractional shares must not kill a whole filing.
# DRIPs and splits produce fractional share counts in transactionShares;
# int("10.5") raised and the per-filing isolation dropped every transaction.
# ---------------------------------------------------------------------------

from moneyflow.ingest.edgar_form4 import parse_form4  # noqa: E402


def test_fractional_shares_parsed_not_dropped():
    xml = _filing_xml([_txn_row(shares=1000, price=50.0), _txn_row(shares="10.5", price=50.0)])
    filing = parse_form4(xml)
    assert len(filing.transactions) == 2
    assert filing.transactions[0].shares == 1000
    assert filing.transactions[1].shares == 10.5
    assert filing.transactions[1].value_usd == 10.5 * 50.0


def test_garbage_shares_still_fail_loud():
    xml = _filing_xml([_txn_row(shares="N/A", price=50.0)])
    try:
        parse_form4(xml)
    except ValueError:
        return
    raise AssertionError("expected ValueError for non-numeric shares")


# ---------------------------------------------------------------------------
# H2 (review 2026-10-02): run_form4 total failure must not mark m4 fresh.
# EFTS search succeeds but every filing fetch/parse/upsert fails ->
# touch() (stale), not mark() (fresh). Partial scans and quiet days keep
# the old behavior (a partial scan with loud errors beats a silent
# 4-day blackout; a genuinely quiet day is a successful run).
# ---------------------------------------------------------------------------


def test_run_form4_total_failure_does_not_mark_fresh(tmp_path):
    from datetime import date

    from moneyflow.store.db import SessionLocal
    from moneyflow.store.repos import FreshnessRepository

    engine = _engine(tmp_path)
    adshs = ["0000000002-26-000001", "0000000003-26-000001"]
    client = _form4_client({}, adshs)  # search ok, every filing fetch 404s
    stats = m4_scan.run_form4(engine, client=client, end=date(2026, 10, 1))
    assert stats["scanned"] == 2 and stats["fetched"] == 0
    assert len(stats["errors"]) == 2
    session = SessionLocal(bind=engine)
    try:
        as_of, checked_at = FreshnessRepository(session).all()["m4"]
    finally:
        session.close()
    assert as_of is None  # touch(), not mark(today)
    assert checked_at is not None


def test_run_form4_partial_failure_still_marks(tmp_path):
    """Partial scan with loud errors -> still marks (loud errors in the
    stats beat a silent blackout)."""
    from datetime import date

    from moneyflow.store.db import SessionLocal
    from moneyflow.store.repos import FreshnessRepository

    engine = _engine(tmp_path)
    good = "0000000002-26-000001"
    bad = "0000000003-26-000001"
    client = _form4_client({good: _BUY_FILING_XML}, [good, bad])
    stats = m4_scan.run_form4(engine, client=client, end=date(2026, 10, 1))
    assert stats["fetched"] == 1 and len(stats["errors"]) == 1
    session = SessionLocal(bind=engine)
    try:
        as_of, _ = FreshnessRepository(session).all()["m4"]
    finally:
        session.close()
    assert as_of is not None and str(as_of) == "2026-10-01"


def test_run_form4_quiet_day_still_marks(tmp_path):
    """No filings in the window is a successful run, not a failure."""
    from datetime import date

    from moneyflow.store.db import SessionLocal
    from moneyflow.store.repos import FreshnessRepository

    engine = _engine(tmp_path)
    client = _form4_client({}, [])
    stats = m4_scan.run_form4(engine, client=client, end=date(2026, 10, 1))
    assert stats["scanned"] == 0 and stats["fetched"] == 0
    assert stats["errors"] == []
    session = SessionLocal(bind=engine)
    try:
        as_of, _ = FreshnessRepository(session).all()["m4"]
    finally:
        session.close()
    assert as_of is not None and str(as_of) == "2026-10-01"


def test_delete_quarter_does_not_commit_alone(tmp_path):
    """H1 atomicity contract: delete_quarter must not commit by itself --
    the amendment path commits delete+upsert together, so a failed upsert
    can never leave a quarter half-deleted."""
    from datetime import date

    from moneyflow.models import ThirteenFHolding
    from moneyflow.store.db import SessionLocal
    from moneyflow.store.repos import ThirteenFHoldingRepository

    engine = _engine(tmp_path)
    session = SessionLocal(bind=engine)
    try:
        repo = ThirteenFHoldingRepository(session)
        repo.upsert_many(
            [
                ThirteenFHolding(
                    report_date=date(2026, 3, 31),
                    filed_at=date(2026, 5, 15),
                    cik="0001649339",
                    issuer="AAA",
                    cusip="111111111",
                    value_usd=1000,
                    shares=10,
                )
            ]
        )
        assert repo.delete_quarter("0001649339", date(2026, 3, 31)) == 1
        session.rollback()  # must restore the row -> delete was uncommitted
        assert len(repo.for_quarter("0001649339", date(2026, 3, 31))) == 1
    finally:
        session.close()
