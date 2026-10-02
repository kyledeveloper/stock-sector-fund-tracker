"""SEC EDGAR 13F-HR ingest (M4).

Fair access: every request goes through PoliteClient (0.5s pacing, well
under SEC's 10 req/s cap; descriptive UA with contact). Pipeline per
manager: submissions JSON -> verify CIK/name -> newest 13F-HR ref ->
filing index -> information-table XML -> parse.

Note: this sandbox's egress gets SEC 403 (confirmed 2026-10-01); the
browser egress returned HTTP 200 for the same URLs. Production runs on
the user's VPS, where the fixtures here were captured from.

Scope (red-team F4, Phase 0): a fixed manager watchlist (M4_WATCHLIST in
models.py, user-approved 2026-10-01), NOT "all filers".

v1 limitation (documented, not silent): 13F XML carries CUSIP + issuer
name but NO ticker. No synthetic CUSIP->ticker mapping in v1 (that would
be fabricated data); the panel shows issuer names. Mapping is a Phase 4+
enhancement. (Form 4 lives in edgar_form4.py.)
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

from moneyflow.common.http import DEFAULT_MIN_INTERVAL_S, DEFAULT_UA, PoliteClient
from moneyflow.models import ThirteenFFilingRef, ThirteenFHolding

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


def recent_13f_refs(submissions: dict, limit: int = 5) -> list[ThirteenFFilingRef]:
    """Newest-first 13F-HR/13F-HR/A refs from a submissions JSON.

    M5: when the newest filing is a cover-only amendment (no info table),
    the fetcher walks this list for the same quarter's base filing instead
    of deadlocking the manager forever.
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
    cands.sort(reverse=True)  # newest reportDate, then newest filingDate
    return [
        ThirteenFFilingRef(
            accession_number=acc,
            filing_date=_parse_date(fdate),
            report_date=_parse_date(rdate),
        )
        for rdate, fdate, acc in cands[:limit]
    ]


def latest_13f_hr(submissions: dict) -> ThirteenFFilingRef:
    """Newest 13F-HR by reportDate (filingDate breaks ties).

    13F-HR/A amendments count: a later amendment supersedes the original
    for its quarter. Index-aligned arrays; length drift fails loud.
    """
    refs = recent_13f_refs(submissions, limit=1)
    if not refs:
        raise ValueError("EDGAR: no 13F-HR filing in submissions")
    return refs[0]


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
        # MINOR-2: sshPrnamtType "PRN" means the number is a dollar principal
        # (bond-like), not a share count. Showing it under "shares" would be
        # wrong data; fail loud until PRN rows get their own handling.
        amt_type = _text(amt, "sshPrnamtType")
        if amt_type and amt_type != "SH":
            raise ValueError(
                f"EDGAR: unsupported shrsOrPrnAmt type '{amt_type}' (need PRN handling)"
            )
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


class _NoInfotableDoc(ValueError):
    """The filing index has no information-table document (e.g. a cover-only
    13F-HR/A). Subclass of ValueError so existing fail-loud tests still hold;
    the fetcher catches this specifically to try the same quarter's base filing."""


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
    if not non_primary:
        # M5: cover-only amendment -- no info table to pick. The fetcher
        # falls back to the same quarter's base filing; this is NOT ambiguity.
        raise _NoInfotableDoc("EDGAR: filing index has no information-table document")
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
    """Full 13F-HR pull for one manager (submissions -> index -> XML -> parse).

    M5: if the newest filing is a cover-only 13F-HR/A (no info table), walk
    back through the same quarter's filings for the base 13F-HR instead of
    raising -- a loud permanent failure for a routine amendment otherwise.
    """
    cik10 = cik.strip().zfill(10)
    own = client is None
    client = client or PoliteClient()
    try:
        sub = client.get(_SUBMISSIONS.format(cik=cik10)).json()
        verify_filer_name(sub, expected_name)
        refs = recent_13f_refs(sub, limit=5)
        if not refs:
            raise ValueError("EDGAR: no 13F-HR filing in submissions")
        same_quarter = [r for r in refs if r.report_date == refs[0].report_date]
        last_err: _NoInfotableDoc | None = None
        for ref in same_quarter:
            acc_nodash = ref.accession_number.replace("-", "")
            index = client.get(_ARCHIVES.format(cik=int(cik10), acc=acc_nodash)).json()
            try:
                doc = _pick_infotable_doc(index)
            except _NoInfotableDoc as e:
                last_err = e
                continue  # cover-only amendment: try the previous filing
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
        raise ValueError(
            f"EDGAR: no filing with an info table for quarter {refs[0].report_date}"
        ) from last_err
    finally:
        if own:
            client.close()
