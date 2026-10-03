"""SEC EDGAR Form 4 ingest: insider-transaction XML + market-wide daily scan (M4).

Parses ownership-document XML (non-derivative transactions only, v1;
derivativeTable ignored) and scans EFTS for recent Form 4/4-A filings.
Shares XML helpers with edgar.py (same package -- allowed by the layering test).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

import httpx

from moneyflow.common.http import PoliteClient
from moneyflow.ingest.edgar import _parse_date, _strip_ns, _text
from moneyflow.models import Form4Filing, InsiderTransaction

_EFTS = "https://efts.sec.gov/LATEST/search-index"


# ---------------------------------------------------------------------------
# Form 4 ownership-document XML (non-derivative transactions only, v1)
# ---------------------------------------------------------------------------


def _is_10b5_1_plan(aff10b5_one: str, footnote_text: str) -> bool:
    """A checkbox or a footnote may mark the trade as a 10b5-1 plan trade.

    MINOR-7: a naive substring match misfires on "NOT pursuant to a 10b5-1
    plan" -- a 10b5-1 mention preceded (within ~40 chars) by "not"/"no" is a
    negation, not a plan trade.
    """
    if aff10b5_one == "1":
        return True
    low = footnote_text.lower()
    for m in re.finditer(r"10b5-1", low):
        before = low[max(0, m.start() - 40) : m.start()]
        if re.search(r"\b(not|no)\b", before):
            continue
        return True
    return False


def parse_form4(xml: bytes, *, accession_number: str = "", form_type: str = "4") -> Form4Filing:
    try:
        root = _strip_ns(ET.fromstring(xml))
    except ET.ParseError as e:
        raise ValueError(f"EDGAR: unparseable Form 4: {e}") from e

    ticker = _text(root, "issuer/issuerTradingSymbol", required=True)
    footnotes = {
        (fn.get("id") or ""): "".join(fn.itertext()).strip() for fn in root.findall(".//footnote")
    }

    # M3: joint filings carry several <reportingOwner> elements. The old code
    # took only the first, which mis-attributed the trade AND silently dropped
    # the filing when the first owner wasn't an officer/director. v1 keeps one
    # filing row: all owner names joined, flags OR'd across owners.
    owners = root.findall("reportingOwner")
    if not owners:
        raise ValueError("EDGAR: Form 4 has no <reportingOwner>")
    names: list[str] = []
    ciks: list[str] = []
    titles: list[str] = []
    is_officer = is_director = is_tenpct = False
    for owner in owners:
        oid = owner.find("reportingOwnerId")
        rel = owner.find("reportingOwnerRelationship")
        names.append(_text(oid, "rptOwnerName"))
        ciks.append(_text(oid, "rptOwnerCik"))
        t = _text(rel, "officerTitle")
        if t:
            titles.append(t)
        is_officer = is_officer or _text(rel, "isOfficer").lower() == "true"
        is_director = is_director or _text(rel, "isDirector").lower() == "true"
        is_tenpct = is_tenpct or _text(rel, "isTenPercentOwner").lower() == "true"

    txs: list[InsiderTransaction] = []
    # B1: ordinal = 0-based row index, part of the PK. Two lots with the same
    # share count at different prices no longer collide.
    for ordinal, node in enumerate(root.findall(".//nonDerivativeTransaction")):
        code = _text(node, "transactionCoding/transactionCode")
        ad = _text(node, "transactionAmounts/transactionAcquiredDisposedCode/value")
        # M1 (review 2026-10-02): fractional shares are legitimate (DRIPs,
        # splits). int("10.5") used to raise and drop the whole filing;
        # float() keeps them. Non-numeric garbage still fails loud.
        shares = float(_text(node, "transactionAmounts/transactionShares/value", required=True))
        price_raw = _text(node, "transactionAmounts/transactionPricePerShare/value")
        price = float(price_raw) if price_raw else None
        footnote_text = " ".join(
            footnotes.get((fid.get("id") or ""), "") for fid in node.findall(".//footnoteId")
        )
        txs.append(
            InsiderTransaction(
                ordinal=ordinal,
                transaction_date=_parse_date(_text(node, "transactionDate/value", required=True)),
                transaction_code=code,
                acquired_disposed=ad,
                shares=shares,
                price=price,
                value_usd=shares * price if price is not None else None,
                side="buy" if ad == "A" else "sell",
                is_open_market_buy=(code == "P" and ad == "A"),
                is_10b5_1=_is_10b5_1_plan(_text(root, "aff10b5One"), footnote_text),
            )
        )

    return Form4Filing(
        ticker=ticker,
        issuer=_text(root, "issuer/issuerName"),
        issuer_cik=_text(root, "issuer/issuerCik"),
        insider="; ".join(n for n in names if n),
        insider_cik=ciks[0] if ciks else "",
        is_joint_filing=len(owners) > 1,
        officer_title="; ".join(titles),
        is_officer=is_officer,
        is_director=is_director,
        is_ten_percent_owner=is_tenpct,
        filed_at=_parse_date(_text(root, "ownerSignature/signatureDate", required=True)),
        accession_number=accession_number,
        form_type=form_type,
        transactions=txs,
    )


# ---------------------------------------------------------------------------
# Form 4 daily scan via EFTS full-text search (market-wide)
# ---------------------------------------------------------------------------


def search_form4(start: date, end: date, client: PoliteClient) -> list[dict]:
    """All Form 4/4-A filings in [start, end] via EFTS (verified 2026-10-01).

    Paginated (size=100). Each hit: {adsh, filename, ciks, file_date, form}.
    _source carries metadata only (no transaction values) -- the XML must
    be fetched per filing. ~560 filings/day observed.
    """
    out: list[dict] = []
    total: int | None = None
    offset = 0
    while True:
        url = (
            f"{_EFTS}?q=%224%22&dateRange=custom"
            f"&startdt={start.isoformat()}&enddt={end.isoformat()}"
            f"&forms=4&from={offset}&size=100"
        )
        data = client.get(url).json()
        hits = (data.get("hits") or {}).get("hits") or []
        if total is None:
            # M7: a missing total used to silently truncate after page 1
            # (250 filings -> 100 returned, no error). Fail loud instead.
            total_raw = (data.get("hits") or {}).get("total")
            if not isinstance(total_raw, dict) or "value" not in total_raw:
                raise ValueError("EDGAR: EFTS response missing hits.total (schema drift)")
            total = total_raw["value"]
        for h in hits:
            src = h.get("_source") or {}
            hid = h.get("_id") or ""
            filename = hid.split(":", 1)[1] if ":" in hid else ""
            if not src.get("adsh") or not filename:
                raise ValueError("EDGAR: EFTS hit missing adsh/filename (drift)")
            out.append(
                {
                    "adsh": src["adsh"],
                    "filename": filename,
                    "ciks": src.get("ciks") or [],
                    "file_date": src.get("file_date") or "",
                    # M2: "4" vs "4/A" -- amendments are flagged in the panel,
                    # not auto-superseded (no reliable original-accession link).
                    "form": src.get("form") or "4",
                }
            )
        offset += len(hits)
        if not hits or (total is not None and offset >= total):
            break
    return out


def fetch_form4_xml(adsh: str, ciks: list[str], filename: str, client: PoliteClient) -> bytes:
    """Fetch a Form 4 document. The Archives path is keyed by filer CIK;
    EFTS returns several CIKs (owners + issuer) without labeling which is
    the archive key, so try each in order (404s fail fast, no retry).
    Fail loud when none serve the document.
    """
    if not ciks:
        raise ValueError(f"EDGAR: no CIKs to locate Form 4 {adsh}")
    acc = adsh.replace("-", "")
    last_404: httpx.HTTPStatusError | None = None
    for cik in ciks:
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{filename}"
        try:
            return client.get(url).content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                last_404 = e
                continue
            raise
    raise ValueError(f"EDGAR: Form 4 document not found under any CIK: {adsh}") from last_404
