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


def test_duplicate_cusip_putcall_rows_are_summed():
    """M3 (review 2026-10-02): the same (cusip, putCall) twice in one info
    table must be summed -- the DB conflict key keeps only one row, so
    last-write-wins would silently drop value. Call legs aggregate
    separately from common stock."""
    xml = (
        b"<informationTable>"
        b"<infoTable><nameOfIssuer>AAA CORP</nameOfIssuer>"
        b"<titleOfClass>COM</titleOfClass><cusip>111111111</cusip>"
        b"<value>1000</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt>"
        b"<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>"
        b"<infoTable><nameOfIssuer>AAA CORP</nameOfIssuer>"
        b"<titleOfClass>COM</titleOfClass><cusip>111111111</cusip>"
        b"<value>2000</value><shrsOrPrnAmt><sshPrnamt>20</sshPrnamt>"
        b"<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>"
        b"<infoTable><nameOfIssuer>AAA CORP</nameOfIssuer>"
        b"<titleOfClass>COM</titleOfClass><cusip>111111111</cusip>"
        b"<putCall>Call</putCall><value>500</value>"
        b"<shrsOrPrnAmt><sshPrnamt>5</sshPrnamt>"
        b"<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>"
        b"</informationTable>"
    )
    rows = parse_13f_infotable(
        xml,
        cik="x",
        filer_name="x",
        report_date=date(2026, 3, 31),
        filed_at=date(2026, 5, 15),
    )
    assert len(rows) == 2
    common = next(r for r in rows if r.put_call == "")
    assert common.value_usd == 3000 and common.shares == 30
    call = next(r for r in rows if r.put_call == "Call")
    assert call.value_usd == 500 and call.shares == 5
