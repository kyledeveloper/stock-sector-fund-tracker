"""SEC EDGAR ingest: 13F-HR holdings + Form 4 insider transactions (M4).

Fair access: every request goes through PoliteClient (0.5s pacing, well
under SEC's 10 req/s cap; descriptive UA with contact). 13F-HR pipeline
per manager: submissions JSON -> verify CIK/name -> newest 13F-HR ref ->
filing index -> information-table XML -> parse.

Note: this sandbox's egress gets SEC 403 (confirmed 2026-10-01); the
browser egress returned HTTP 200 for the same URLs. Production runs on
the user's VPS, where the fixtures here were captured from.

Scope (red-team F4, Phase 0): a fixed manager watchlist (M4_WATCHLIST in
models.py, user-approved 2026-10-01), NOT "all filers".

v1 limitations (documented, not silent):
- 13F XML carries CUSIP + issuer name but NO ticker. No synthetic
  CUSIP->ticker mapping in v1 (that would be fabricated data); the panel
  shows issuer names. Mapping is a Phase 4+ enhancement.
- Form 4: non-derivative transactions only; derivativeTable ignored.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

from moneyflow.common.http import DEFAULT_MIN_INTERVAL_S, DEFAULT_UA, PoliteClient
from moneyflow.models import (
    Form4Filing,
    InsiderTransaction,
    ThirteenFFilingRef,
    ThirteenFHolding,
)

USER_AGENT = DEFAULT_UA
MIN_INTERVAL_S = DEFAULT_MIN_INTERVAL_S

_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"


def _strip_ns(root: ET.Element) -> ET.Element:
    """Make parsing namespace-agnostic (13F docs declare sec.gov namespaces)."""
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _text(el: ET.Element | None, path: str, *, required: bool = False) -> str:
    node = el.find(path) if el is not None else None
    val = (node.text or "").strip() if node is not None else ""
    if required and not val:
        raise ValueError(f"EDGAR: missing required <{path}> in payload")
    return val


def _parse_date(s: str) -> date:
    return date.fromisoformat(s.strip())


# ---------------------------------------------------------------------------
# submissions JSON: newest 13F-HR ref + CIK/name gate
# ---------------------------------------------------------------------------


def latest_13f_hr(submissions: dict) -> ThirteenFFilingRef:
    """Newest 13F-HR by reportDate (filingDate breaks ties).

    13F-HR/A amendments count: a later amendment supersedes the original
    for its quarter. Index-aligned arrays; length drift fails loud.
    """
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accs = recent.get("accessionNumber") or []
    fdates = recent.get("filingDate") or []
    rdates = recent.get("reportDate") or []
    n = len(forms)
    if not (len(accs) == len(fdates) == len(rdates) == n):
        raise ValueError("EDGAR: submissions arrays misaligned (upstream drift)")
    cands: list[tuple[str, str, str]] = []  # (reportDate, filingDate, accession)
    for i, form in enumerate(forms):
        if form in ("13F-HR", "13F-HR/A"):
            cands.append((rdates[i], fdates[i], accs[i]))
    if not cands:
        raise ValueError("EDGAR: no 13F-HR filing in submissions")
    cands.sort(reverse=True)  # newest reportDate, then newest filingDate
    rdate, fdate, acc = cands[0]
    return ThirteenFFilingRef(
        accession_number=acc,
        filing_date=_parse_date(fdate),
        report_date=_parse_date(rdate),
    )


def verify_filer_name(submissions: dict, expected: str) -> None:
    """CIK<->name gate: the watchlist is only as trustworthy as this check.

    `expected` is a short display name; it must appear (case-insensitive)
    in EDGAR's registered name. A hijacked or mistyped CIK fails loud
    before any holdings are attributed to the wrong manager.
    """
    actual = (submissions.get("name") or "").strip()
    if expected.lower() not in actual.lower():
        raise ValueError(f"EDGAR CIK/name mismatch: expected '{expected}' in registered '{actual}'")


# ---------------------------------------------------------------------------
# 13F-HR information-table XML
# ---------------------------------------------------------------------------


def parse_13f_infotable(
    xml: bytes,
    *,
    cik: str,
    filer_name: str,
    report_date: date,
    filed_at: date,
) -> list[ThirteenFHolding]:
    try:
        root = _strip_ns(ET.fromstring(xml))
    except ET.ParseError as e:
        raise ValueError(f"EDGAR: unparseable 13F info table: {e}") from e
    rows = root.findall(".//infoTable")
    if not rows:
        raise ValueError("EDGAR: no <infoTable> rows in 13F payload")
    out: list[ThirteenFHolding] = []
    for row in rows:
        amt = row.find("shrsOrPrnAmt")
        out.append(
            ThirteenFHolding(
                report_date=report_date,
                filed_at=filed_at,
                cik=cik,
                filer_name=filer_name,
                issuer=_text(row, "nameOfIssuer", required=True),
                cusip=_text(row, "cusip", required=True),
                title_of_class=_text(row, "titleOfClass"),
                value_usd=float(_text(row, "value", required=True)),
                shares=int(_text(amt, "sshPrnamt", required=True)),
                put_call=_text(row, "putCall"),
            )
        )
    return out


def _pick_infotable_doc(index_json: dict) -> str:
    """Choose the information-table XML from a filing index (directory listing).

    Never guess between several candidates: prefer *info*table* names, take
    the single non-primary XML if unambiguous, else fail loud.
    """
    items = ((index_json.get("directory") or {}).get("item")) or []
    docs = [it.get("name", "") for it in items if it.get("name", "").endswith(".xml")]
    if not docs:
        raise ValueError("EDGAR: no XML documents in filing index")
    non_primary = [d for d in docs if d.lower() != "primary_doc.xml"]
    preferred = [d for d in non_primary if re.search(r"info.?table", d, re.I)]
    if len(preferred) == 1:
        return preferred[0]
    if not preferred and len(non_primary) == 1:
        return non_primary[0]
    raise ValueError(f"EDGAR: ambiguous info-table candidates: {docs}")


def peek_latest_13f(
    cik: str, expected_name: str, client: PoliteClient
) -> tuple[ThirteenFFilingRef, str]:
    """Cheap daily check: submissions JSON only (no filing download).

    Returns (newest 13F-HR ref, EDGAR registered name). The service
    compares ref.report_date against stored quarters and only full-fetches
    when a new quarter appeared -- 12 tiny requests/day instead of 36.
    """
    cik10 = cik.strip().zfill(10)
    sub = client.get(_SUBMISSIONS.format(cik=cik10)).json()
    verify_filer_name(sub, expected_name)
    return latest_13f_hr(sub), (sub.get("name") or "").strip()


def fetch_13f_holdings(
    cik: str,
    expected_name: str,
    client: PoliteClient | None = None,
) -> list[ThirteenFHolding]:
    """Full 13F-HR pull for one manager (submissions -> index -> XML -> parse)."""
    cik10 = cik.strip().zfill(10)
    own = client is None
    client = client or PoliteClient()
    try:
        sub = client.get(_SUBMISSIONS.format(cik=cik10)).json()
        verify_filer_name(sub, expected_name)
        ref = latest_13f_hr(sub)
        acc_nodash = ref.accession_number.replace("-", "")
        index = client.get(_ARCHIVES.format(cik=int(cik10), acc=acc_nodash)).json()
        doc = _pick_infotable_doc(index)
        xml = client.get(
            f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{acc_nodash}/{doc}"
        ).content
        return parse_13f_infotable(
            xml,
            cik=cik10,
            filer_name=(sub.get("name") or "").strip(),
            report_date=ref.report_date,
            filed_at=ref.filing_date,
        )
    finally:
        if own:
            client.close()


# ---------------------------------------------------------------------------
# Form 4 ownership-document XML (non-derivative transactions only, v1)
# ---------------------------------------------------------------------------


def parse_form4(xml: bytes, *, accession_number: str = "") -> Form4Filing:
    try:
        root = _strip_ns(ET.fromstring(xml))
    except ET.ParseError as e:
        raise ValueError(f"EDGAR: unparseable Form 4: {e}") from e

    ticker = _text(root, "issuer/issuerTradingSymbol", required=True)
    owner = root.find("reportingOwner")
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    footnotes = {
        (fn.get("id") or ""): "".join(fn.itertext()).strip() for fn in root.findall(".//footnote")
    }

    def flag(path: str) -> bool:
        return _text(rel, path).lower() == "true"

    txs: list[InsiderTransaction] = []
    for node in root.findall(".//nonDerivativeTransaction"):
        code = _text(node, "transactionCoding/transactionCode")
        ad = _text(node, "transactionAmounts/transactionAcquiredDisposedCode/value")
        shares = int(_text(node, "transactionAmounts/transactionShares/value", required=True))
        price_raw = _text(node, "transactionAmounts/transactionPricePerShare/value")
        price = float(price_raw) if price_raw else None
        footnote_text = " ".join(
            footnotes.get((fid.get("id") or ""), "") for fid in node.findall(".//footnoteId")
        )
        txs.append(
            InsiderTransaction(
                transaction_date=_parse_date(_text(node, "transactionDate/value", required=True)),
                transaction_code=code,
                acquired_disposed=ad,
                shares=shares,
                price=price,
                value_usd=shares * price if price is not None else None,
                side="buy" if ad == "A" else "sell",
                is_open_market_buy=(code == "P" and ad == "A"),
                is_10b5_1=(_text(root, "aff10b5One") == "1" or "10b5-1" in footnote_text.lower()),
            )
        )

    owner_id = owner.find("reportingOwnerId") if owner is not None else None
    return Form4Filing(
        ticker=ticker,
        issuer=_text(root, "issuer/issuerName"),
        issuer_cik=_text(root, "issuer/issuerCik"),
        insider=_text(owner_id, "rptOwnerName"),
        insider_cik=_text(owner_id, "rptOwnerCik"),
        officer_title=_text(rel, "officerTitle"),
        is_officer=flag("isOfficer"),
        is_director=flag("isDirector"),
        is_ten_percent_owner=flag("isTenPercentOwner"),
        filed_at=_parse_date(_text(root, "ownerSignature/signatureDate", required=True)),
        accession_number=accession_number,
        transactions=txs,
    )
