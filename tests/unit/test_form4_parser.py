"""RED: Form 4 (insider transactions) XML parser contract.

Fixture: tests/fixtures/edgar/form4_samsara.xml — real Form 4, Samsara
Inc (IOT), CEO Sanjit Biswas, filed 2026-10-01. Trimmed to 2 sell
transactions (the original had 12, all code S via 10b5-1 plans).
Buy-side classification is tested with a synthetic inline P/A row:
fixtures stay 100% real.
"""

from pathlib import Path

from moneyflow.ingest.edgar import parse_form4

FIXTURE = Path(__file__).parent.parent / "fixtures" / "edgar" / "form4_samsara.xml"

_BUY_XML = """<ownershipDocument><issuer><issuerTradingSymbol>XYZ</issuerTradingSymbol>
<issuerName>Xyz Inc.</issuerName></issuer><reportingOwner><reportingOwnerId>
<rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId><reportingOwnerRelationship>
<isDirector>false</isDirector><isOfficer>true</isOfficer><officerTitle>CFO</officerTitle>
</reportingOwnerRelationship></reportingOwner>
<nonDerivativeTable><nonDerivativeTransaction>
<transactionDate><value>2026-09-28</value></transactionDate>
<transactionCoding><transactionCode>P</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>1000</value></transactionShares>
<transactionPricePerShare><value>50.5</value></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
</transactionAmounts></nonDerivativeTransaction></nonDerivativeTable>
<ownerSignature><signatureDate>2026-09-29</signatureDate></ownerSignature>
</ownershipDocument>"""


def test_header_fields():
    f = parse_form4(FIXTURE.read_bytes())
    assert f.ticker == "IOT"
    assert f.issuer == "Samsara Inc."
    assert f.insider == "Biswas Sanjit"
    assert f.is_officer and f.is_director
    assert f.officer_title == "CHIEF EXECUTIVE OFFICER"
    assert str(f.filed_at) == "2026-10-01"


def test_sell_transactions_classified():
    f = parse_form4(FIXTURE.read_bytes())
    assert len(f.transactions) == 2
    t0 = f.transactions[0]
    assert t0.side == "sell"
    assert t0.transaction_code == "S"
    assert t0.shares == 101968
    assert t0.price == 37.6769
    assert t0.value_usd == 101968 * 37.6769
    assert str(t0.transaction_date) == "2026-09-29"
    assert not t0.is_open_market_buy


def test_10b5_1_plan_detected():
    f = parse_form4(FIXTURE.read_bytes())
    assert f.transactions[0].is_10b5_1 is True  # aff10b5One=1 + F1 footnote


def test_buy_side_classification_synthetic():
    f = parse_form4(_BUY_XML.encode())
    assert len(f.transactions) == 1
    t = f.transactions[0]
    assert t.side == "buy"
    assert t.is_open_market_buy is True  # code P + acquired
    assert t.value_usd == 1000 * 50.5
    assert f.ticker == "XYZ"


def test_missing_ticker_fails_loud():
    bad = _BUY_XML.replace("<issuerTradingSymbol>XYZ</issuerTradingSymbol>", "")
    try:
        parse_form4(bad.encode())
    except ValueError as e:
        assert "ticker" in str(e).lower() or "symbol" in str(e).lower()
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
