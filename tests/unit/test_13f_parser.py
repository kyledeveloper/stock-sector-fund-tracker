"""RED: 13F-HR information-table XML parser contract.

Fixture: tests/fixtures/edgar/scion_infotable.xml — real Scion 13F-HR
info table (filed 2025-11-03, report 2025-09-30), 8 rows, including
put/call option legs (red-team: option legs must not be mistaken for
common-stock positions).
"""

from datetime import date
from pathlib import Path

from moneyflow.ingest.edgar import parse_13f_infotable

FIXTURE = Path(__file__).parent.parent / "fixtures" / "edgar" / "scion_infotable.xml"


def _rows():
    return parse_13f_infotable(
        FIXTURE.read_bytes(),
        cik="0001649339",
        filer_name="Scion Asset Management, LLC",
        report_date=date(2025, 9, 30),
        filed_at=date(2025, 11, 3),
    )


def test_parses_all_eight_rows():
    assert len(_rows()) == 8


def test_common_stock_row_fields():
    rows = _rows()
    lulu = next(r for r in rows if r.cusip == "550021109")
    assert lulu.issuer == "LULULEMON ATHLETICA INC"
    assert lulu.title_of_class == "COM"
    assert lulu.value_usd == 17793000
    assert lulu.shares == 100000
    assert lulu.put_call == ""  # no putCall element = common stock
    assert lulu.report_date == date(2025, 9, 30)
    assert lulu.cik == "0001649339"


def test_option_legs_keep_put_call_flag():
    rows = _rows()
    pltr = next(r for r in rows if r.cusip == "69608A108")
    assert pltr.put_call == "Put"
    assert pltr.value_usd == 912100000
    assert pltr.shares == 5000000
    pfe = next(r for r in rows if r.cusip == "717081103")
    assert pfe.put_call == "Call"


def test_pref_stock_row():
    rows = _rows()
    brk = next(r for r in rows if r.cusip == "116794207")
    assert brk.title_of_class == "6.375 PREF SER A"
    assert brk.value_usd == 13137181


def test_malformed_xml_fails_loud():
    try:
        parse_13f_infotable(
            b"<infoTable><unclosed>",
            cik="x",
            filer_name="x",
            report_date=date(2025, 9, 30),
            filed_at=date(2025, 11, 3),
        )
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
