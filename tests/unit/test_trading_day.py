"""Trading-day calendar tests (red-team M4).

The pipeline must never file Friday's data under Saturday's date.
freezegun pins "today" so the gate logic is deterministic.
"""

from __future__ import annotations

from datetime import date, timedelta

from moneyflow.common.trading_day import (
    is_stale,
    is_trading_day,
    last_trading_day_before,
)


def test_weekends_are_not_trading_days():
    assert not is_trading_day(date(2026, 10, 3))  # Saturday
    assert not is_trading_day(date(2026, 10, 4))  # Sunday


def test_weekday_is_trading_day():
    assert is_trading_day(date(2026, 10, 2))  # Friday


def test_nyse_holidays_observed():
    assert not is_trading_day(date(2026, 11, 26))  # Thanksgiving
    assert not is_trading_day(date(2026, 12, 25))  # Christmas (Friday)
    assert not is_trading_day(date(2026, 7, 3))  # Independence Day observed


def test_last_trading_day_before_monday_is_friday():
    assert last_trading_day_before(date(2026, 10, 5)) == date(2026, 10, 2)


def test_last_trading_day_before_tuesday_is_monday():
    assert last_trading_day_before(date(2026, 10, 6)) == date(2026, 10, 5)


def test_stale_rule_is_t_plus_1_not_calendar_days():
    # Monday: Friday's data is the latest available -> NOT stale.
    assert not is_stale(date(2026, 10, 2), date(2026, 10, 5))
    # Tuesday: Monday's data is expected -> Friday's IS stale.
    assert is_stale(date(2026, 10, 2), date(2026, 10, 6))
    # No data at all -> stale.
    assert is_stale(None, date(2026, 10, 5))


def test_future_as_of_is_stale():
    # Red-team m1: a misprinted future "As of" date must never read "fresh".
    assert is_stale(date(2027, 1, 5), date(2026, 10, 5))


def test_long_weekend_monday_holiday():
    # Red-team m3: Labor Day Mon 2026-09-07 -> on Tue 9/8, Friday's data
    # is still the latest available -> NOT stale.
    assert not is_stale(date(2026, 9, 4), date(2026, 9, 8))


# --- Auditor P1 #3: calendar coverage through 2028 + loud exhaustion ---

import pytest  # noqa: E402

from moneyflow.common import trading_day as td  # noqa: E402

# Cross-checked against exchange_calendars XNYS on 2026-10-18.
NYSE_2028 = [
    date(2028, 1, 17),
    date(2028, 2, 21),
    date(2028, 4, 14),
    date(2028, 5, 29),
    date(2028, 6, 19),
    date(2028, 7, 4),
    date(2028, 9, 4),
    date(2028, 11, 23),
    date(2028, 12, 25),
]


def test_2028_holidays_are_closed():
    for d in NYSE_2028:
        assert not td.is_trading_day(d), d


def test_new_year_2028_on_saturday_is_not_observed_friday():
    assert td.is_trading_day(date(2027, 12, 31))  # NYSE skips the Friday observance


def test_beyond_calendar_end_fails_loud():
    with pytest.raises(td.CalendarExhausted, match="extend NYSE_HOLIDAYS"):
        td.is_trading_day(td.CALENDAR_END + timedelta(days=1))


def test_days_left_and_warning_window():
    assert td.calendar_days_left(td.CALENDAR_END) == 0
    assert td.calendar_warning(date(2026, 10, 18)) is None
    msg = td.calendar_warning(td.CALENDAR_END - timedelta(days=30))
    assert msg is not None and "30 days" in msg


def test_is_stale_past_calendar_end_reports_stale_instead_of_raising(caplog):
    """Auditor low #5: read paths (API freshness/sentiment) must degrade to
    stale, not 500, once the holiday table runs out. The pipeline still
    fails loud via is_trading_day."""
    from moneyflow.common import trading_day as td

    after = td.CALENDAR_END + timedelta(days=10)
    with caplog.at_level("WARNING", logger="moneyflow.common.trading_day"):
        assert td.is_stale(after - timedelta(days=1), after) is True
    assert "CALENDAR_END" in caplog.text
