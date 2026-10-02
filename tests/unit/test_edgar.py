"""RED: EDGAR submissions-JSON contract + client compliance.

Fixture: tests/fixtures/edgar/scion_submissions.json — hand-built from
the real shape of data.sec.gov/submissions/CIK0001649339.json
(index-aligned arrays under filings.recent; captured 2026-10-01).

Contract under test (moneyflow.ingest.edgar):
- latest_13f_hr(): newest reportDate wins; filingDate breaks ties;
  13F-HR and 13F-HR/A both count (amendments supersede).
- verify_filer_name(): CIK<->name gate -- a hijacked/wrong CIK must
  fail loud before any fetch (the 12-manager watchlist is only as
  trustworthy as this check).
- Client: SEC fair-access requires a descriptive UA with contact and
  <=10 req/s. Reuses PoliteClient (0.5s pacing); the UA must carry
  project identity + contact.
"""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from moneyflow.common.http import PoliteClient
from moneyflow.ingest.edgar import (
    MIN_INTERVAL_S,
    USER_AGENT,
    _pick_infotable_doc,
    fetch_13f_holdings,
    latest_13f_hr,
    parse_13f_infotable,
    verify_filer_name,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "edgar" / "scion_submissions.json"


def test_latest_13f_hr_selection():
    sel = latest_13f_hr(json.loads(FIXTURE.read_text()))
    assert sel.accession_number == "0001649339-25-000007"
    assert sel.filing_date == date(2025, 11, 3)
    assert sel.report_date == date(2025, 9, 30)


def test_amendment_for_same_quarter_wins_by_filing_date():
    payload = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001-26-000002", "0001-26-000001"],
                "filingDate": ["2026-02-10", "2026-02-01"],
                "form": ["13F-HR/A", "13F-HR"],
                "reportDate": ["2025-12-31", "2025-12-31"],
            }
        }
    }
    sel = latest_13f_hr(payload)
    assert sel.accession_number == "0001-26-000002"  # later amendment supersedes


def test_no_13f_hr_fails_loud():
    payload = {
        "filings": {
            "recent": {"accessionNumber": [], "filingDate": [], "form": [], "reportDate": []}
        }
    }
    with pytest.raises(ValueError, match="13F-HR"):
        latest_13f_hr(payload)


def test_filer_name_verification():
    payload = json.loads(FIXTURE.read_text())
    verify_filer_name(payload, "Scion Asset Management, LLC")  # exact ok
    with pytest.raises(ValueError, match="[Cc][Ii][Kk]"):
        verify_filer_name(payload, "Someone Else Entirely")


def test_client_compliance():
    assert "us-moneyflow" in USER_AGENT  # project identity
    assert "http" in USER_AGENT  # contact surface (repo URL)
    assert MIN_INTERVAL_S >= 0.1  # <=10 req/s per SEC fair-access


# --- fetch_13f_holdings full pull via MockTransport (offline) ---

_FIXDIR = Path(__file__).parent.parent / "fixtures" / "edgar"


def _mock_client() -> PoliteClient:
    submissions = json.loads((_FIXDIR / "scion_submissions.json").read_text())
    # strip the _note helper key (not part of the real payload)
    submissions.pop("_note", None)
    infotable = (_FIXDIR / "scion_infotable.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("CIK0001649339.json"):
            return httpx.Response(200, json=submissions)
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
            return httpx.Response(200, content=infotable)
        return httpx.Response(404, text="not found")

    return PoliteClient(transport=httpx.MockTransport(handler), trust_env=False)


def test_fetch_13f_holdings_end_to_end():
    rows = fetch_13f_holdings("1649339", "Scion Asset Management", client=_mock_client())
    assert len(rows) == 8
    assert rows[0].cik == "0001649339"  # zero-padded
    assert rows[0].filer_name == "Scion Asset Management, LLC"  # EDGAR name
    assert str(rows[0].report_date) == "2025-09-30"


def test_fetch_fails_loud_on_name_mismatch():
    with pytest.raises(ValueError, match="[Cc][Ii][Kk]"):
        fetch_13f_holdings("1649339", "Totally Wrong Name", client=_mock_client())


def test_pick_infotable_doc_ambiguous():
    with pytest.raises(ValueError, match="ambiguous"):
        _pick_infotable_doc(
            {
                "directory": {
                    "item": [
                        {"name": "primary_doc.xml"},
                        {"name": "a.xml"},
                        {"name": "b.xml"},
                    ]
                }
            }
        )


def test_pick_infotable_doc_no_xml():
    with pytest.raises(ValueError, match="no XML"):
        _pick_infotable_doc({"directory": {"item": [{"name": "a.txt"}]}})


def test_cover_only_amendment_falls_back_to_base_filing():
    """M5: newest filing is a cover-only 13F-HR/A (index has primary_doc.xml
    only). The fetcher must use the same quarter's base filing instead of
    raising -- previously a loud permanent per-manager deadlock."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "submissions/CIK" in url:
            return httpx.Response(
                200,
                json={
                    "name": "Scion Asset Management, LLC",
                    "filings": {
                        "recent": {
                            "accessionNumber": [
                                "0001649339-25-000007",  # cover-only /A (newest)
                                "0001649339-25-000006",  # base 13F-HR, same quarter
                            ],
                            "filingDate": ["2025-11-03", "2025-08-14"],
                            "form": ["13F-HR/A", "13F-HR"],
                            "reportDate": ["2025-09-30", "2025-09-30"],
                        }
                    },
                },
            )
        if url.endswith("index.json"):
            if "000164933925000007" in url:  # the amendment: cover only
                return httpx.Response(
                    200, json={"directory": {"item": [{"name": "primary_doc.xml"}]}}
                )
            return httpx.Response(
                200,
                json={
                    "directory": {"item": [{"name": "primary_doc.xml"}, {"name": "infotable.xml"}]}
                },
            )
        if url.endswith("infotable.xml"):
            return httpx.Response(200, content=(_FIXDIR / "scion_infotable.xml").read_bytes())
        return httpx.Response(404, text="not found")

    client = PoliteClient(transport=httpx.MockTransport(handler), trust_env=False, min_interval_s=0)
    holdings = fetch_13f_holdings("1649339", "Scion", client=client)
    assert len(holdings) == 8  # base filing's info table, not an exception
    assert str(holdings[0].report_date) == "2025-09-30"


def test_pick_infotable_cover_only_raises_distinct_error():
    """The cover-only case raises _NoInfotableDoc (a ValueError subclass):
    the fetcher falls back on it, genuine ambiguity still fails loud."""
    from moneyflow.ingest.edgar import _NoInfotableDoc

    with pytest.raises(_NoInfotableDoc):
        _pick_infotable_doc({"directory": {"item": [{"name": "primary_doc.xml"}]}})
    with pytest.raises(ValueError, match="ambiguous"):
        _pick_infotable_doc(
            {
                "directory": {
                    "item": [
                        {"name": "primary_doc.xml"},
                        {"name": "a.xml"},
                        {"name": "b.xml"},
                    ]
                }
            }
        )


def test_parse_13f_prn_amt_type_fails_loud():
    """MINOR-2: a PRN (principal amount) row must not masquerade as shares."""
    xml = b"""<informationTable>
<infoTable><nameOfIssuer>X</nameOfIssuer><cusip>000000000</cusip>
<titleOfClass>COM</titleOfClass><value>1000</value>
<shrsOrPrnAmt><sshPrnamt>500</sshPrnamt><sshPrnamtType>PRN</sshPrnamtType></shrsOrPrnAmt>
</infoTable></informationTable>"""
    with pytest.raises(ValueError, match="PRN"):
        parse_13f_infotable(
            xml,
            cik="0000000001",
            filer_name="X",
            report_date=date(2026, 6, 30),
            filed_at=date(2026, 8, 14),
        )
