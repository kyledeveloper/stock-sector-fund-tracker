"""Trading-day calendar tests (red-team M4).

The pipeline must never file Friday's data under Saturday's date.
freezegun pins "today" so the gate logic is deterministic.
"""

from __future__ import annotations

from datetime import date

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
