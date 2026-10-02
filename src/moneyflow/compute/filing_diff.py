"""QoQ diff of 13F holdings (pure functions, no I/O).

Keyed by (cusip, put_call): the same CUSIP can appear twice (common
stock + option leg, e.g. Scion's HAL) and those are independent
positions -- keying by cusip alone would silently merge them.
"""

from __future__ import annotations

from moneyflow.models import ThirteenFHolding, ThirteenFPositionView


def _key(h: ThirteenFHolding) -> tuple[str, str]:
    return (h.cusip, h.put_call)


def _view(
    h: ThirteenFHolding, status: str, delta: float, prev: float | None
) -> ThirteenFPositionView:
    return ThirteenFPositionView(
        report_date=h.report_date,
        filed_at=h.filed_at,
        cik=h.cik,
        filer_name=h.filer_name,
        issuer=h.issuer,
        cusip=h.cusip,
        value_usd=h.value_usd if status != "exited" else 0.0,
        shares=h.shares if status != "exited" else 0,
        put_call=h.put_call,
        status=status,
        value_delta_usd=delta,
        prev_value_usd=prev,
    )


def diff_13f(
    prev: list[ThirteenFHolding], cur: list[ThirteenFHolding]
) -> list[ThirteenFPositionView]:
    """Diff two quarters of one manager's holdings.

    `prev` may be empty (first quarter on record -> everything "new").
    Output: current positions sorted by value desc, then exited positions
    sorted by prior value desc.
    """
    prev_by = {_key(h): h for h in prev}
    seen: set[tuple[str, str]] = set()
    out: list[ThirteenFPositionView] = []
    for h in cur:
        p = prev_by.get(_key(h))
        seen.add(_key(h))
        if p is None:
            out.append(_view(h, "new", h.value_usd, None))
        elif h.value_usd > p.value_usd:
            out.append(_view(h, "increased", h.value_usd - p.value_usd, p.value_usd))
        elif h.value_usd < p.value_usd:
            out.append(_view(h, "decreased", h.value_usd - p.value_usd, p.value_usd))
        else:
            out.append(_view(h, "unchanged", 0.0, p.value_usd))
    for p in prev:
        if _key(p) not in seen:
            out.append(_view(p, "exited", -p.value_usd, p.value_usd))
    current = [v for v in out if v.status != "exited"]
    exited = [v for v in out if v.status == "exited"]
    current.sort(key=lambda v: v.value_usd, reverse=True)
    exited.sort(key=lambda v: v.prev_value_usd or 0.0, reverse=True)
    return current + exited
