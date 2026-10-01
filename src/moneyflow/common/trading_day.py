"""US equity market calendar for the daily pipeline (red-team M4).

The timer fires every day, but writes only happen on trading days --
this module is the gate that stops Friday's data being filed under
Saturday's date. Static NYSE holiday list; extend each December.
All dates are America/New_York calendar days.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# NYSE holidays, observed dates. Source: NYSE calendar.
NYSE_HOLIDAYS: frozenset[date] = frozenset(
    {
        # 2026
        date(2026, 1, 1),  # New Year's Day
        date(2026, 1, 19),  # Martin Luther King Jr. Day
        date(2026, 2, 16),  # Presidents' Day
        date(2026, 4, 3),  # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),  # Independence Day (observed)
        date(2026, 9, 7),  # Labor Day
        date(2026, 11, 26),  # Thanksgiving
        date(2026, 12, 25),  # Christmas
        # 2027
        date(2027, 1, 1),  # New Year's Day
        date(2027, 1, 18),  # Martin Luther King Jr. Day
        date(2027, 2, 15),  # Presidents' Day
        date(2027, 3, 26),  # Good Friday
        date(2027, 5, 31),  # Memorial Day
        date(2027, 6, 18),  # Juneteenth (observed)
        date(2027, 7, 5),  # Independence Day (observed)
        date(2027, 9, 6),  # Labor Day
        date(2027, 11, 25),  # Thanksgiving
        date(2027, 12, 24),  # Christmas (observed)
    }
)


def is_trading_day(d: date) -> bool:
    """True for Mon-Fri that is not an NYSE holiday."""
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def last_trading_day_before(d: date) -> date:
    """Most recent trading day strictly before d."""
    candidate = d - timedelta(days=1)
    while not is_trading_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def is_stale(as_of: date | None, today: date) -> bool:
    """Freshness rule (T+1): data for the last trading day before today
    is expected. Older (or missing) -> stale, panel grays out.
    A future as_of (misprinted file date) is also stale, never "fresh"."""
    if as_of is None:
        return True
    if as_of > today:
        return True
    return as_of < last_trading_day_before(today)


def today_et() -> date:
    """Current calendar date in America/New_York (all storage is ET)."""
    return datetime.now(ET).date()
