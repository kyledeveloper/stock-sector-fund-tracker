"""RED (now green): pure QoQ diff of 13F holdings."""

from datetime import date

from moneyflow.compute.filing_diff import diff_13f
from moneyflow.models import ThirteenFHolding


def _h(cusip: str, value: float, put_call: str = "", **kw) -> ThirteenFHolding:
    return ThirteenFHolding(
        report_date=date(2026, 6, 30),
        filed_at=date(2026, 8, 14),
        cik="0001649339",
        filer_name="Scion",
        issuer=f"ISSUER-{cusip}",
        cusip=cusip,
        value_usd=value,
        shares=100,
        put_call=put_call,
        **kw,
    )


def test_statuses():
    prev = [_h("A", 100.0), _h("B", 200.0), _h("C", 300.0), _h("D", 400.0)]
    cur = [_h("A", 150.0), _h("B", 150.0), _h("C", 300.0), _h("E", 500.0)]
    views = {v.cusip: v for v in diff_13f(prev, cur)}
    assert views["A"].status == "increased" and views["A"].value_delta_usd == 50.0
    assert views["B"].status == "decreased" and views["B"].value_delta_usd == -50.0
    assert views["C"].status == "unchanged"
    assert views["E"].status == "new" and views["E"].prev_value_usd is None
    assert views["D"].status == "exited" and views["D"].value_usd == 0


def test_empty_prev_all_new():
    views = diff_13f([], [_h("A", 100.0)])
    assert len(views) == 1 and views[0].status == "new"


def test_option_leg_keyed_separately_from_common():
    # Same CUSIP as common stock AND a call leg: independent positions.
    prev = [_h("HAL", 100.0, ""), _h("HAL", 50.0, "Call")]
    cur = [_h("HAL", 100.0, ""), _h("HAL", 80.0, "Call")]
    views = diff_13f(prev, cur)
    by_key = {(v.cusip, v.put_call): v for v in views}
    assert by_key[("HAL", "")].status == "unchanged"
    assert by_key[("HAL", "Call")].status == "increased"


def test_sorted_current_by_value_then_exited():
    prev = [_h("X", 999.0)]
    cur = [_h("B", 100.0), _h("A", 500.0)]
    views = diff_13f(prev, cur)
    assert [v.cusip for v in views] == ["A", "B", "X"]
    assert views[-1].status == "exited"
