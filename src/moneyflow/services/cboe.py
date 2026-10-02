"""M5 orchestration: CBOE daily put/call ratio -> sentiment panel (thin layer).

The parser is a pure function (no network, no DB): page text in, CboeDaily
(or None for weekend/holiday no-data pages) out. The scraper fetches one
page per day through PoliteClient. The service wires fetch -> parse ->
repo -> freshness. Idempotent by upsert; fail-loud on garbled pages.

ToS note (recorded for the user's M5 decision 2026-10-01): robots.txt does
not block the daily statistics page, but CBOE Terms Section 2 conflicts
with the planned daily scrape + 90-day stored history. Implemented as
directed; revisit if CBOE blocks or the terms change.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime, timedelta

from moneyflow.common.http import PoliteClient
from moneyflow.common.trading_day import is_trading_day, last_trading_day_before, today_et
from moneyflow.models import CboeDaily
from moneyflow.store.db import SessionLocal
from moneyflow.store.repos import CboePutCallRepository, FreshnessRepository

logger = logging.getLogger(__name__)

CBOE_DAILY_URL = "https://www.cboe.com/markets/us/options/market-statistics/daily"

#: The three scopes the panel needs; a page must carry all three or fail loud.
_SCOPES: tuple[tuple[str, str], ...] = (
    ("total", "TOTAL PUT/CALL RATIO"),
    ("index", "INDEX PUT/CALL RATIO"),
    ("equity", "EQUITY PUT/CALL RATIO"),
)

#: Values that mean "no quote published" rather than a number.
_NO_VALUE = {"", "--", "—", "n/a", "na", "null", "none"}

#: Sanity bound: a genuine daily put/call ratio lives in [0, 5].
#: CBOE total/equity ratios rarely leave 0.5-1.5; index ratios run higher
#: but readings above 5 are essentially unprecedented. A 10x decimal shift
#: (0.88 -> 8.8) or 100x shift (0.25 -> 25) lands above 5 -> fail loud.
#: A shift landing *inside* [0, 5] is indistinguishable from genuine data
#: and cannot be caught by range alone -- accepted, documented limitation.
_MAX_RATIO = 5.0

#: Marker identifying a genuine CBOE daily-statistics page. A page without
#: any ratio rows is a no-data day (weekend/holiday) -> return None and let
#: the caller skip the write. A page without the marker at all is an
#: unknown structure -> fail loud instead of silently treating a site
#: redesign as "no data".
_PAGE_MARKER = "Daily Market Statistics"


class CboeParseError(Exception):
    """The page structure or a ratio value is not what we expect. Fail loud."""


def _table_values(html: str) -> dict[str, str]:
    """Rendered table rows: <td ...>NAME PUT/CALL RATIO</td><td ...>VALUE</td>."""
    out: dict[str, str] = {}
    for key, name in _SCOPES:
        m = re.search(
            r"<td[^>]*>" + re.escape(name) + r"</td>\s*<td[^>]*>([^<]*)</td>",
            html,
        )
        if m:
            out[key] = m.group(1)
    return out


def _rsc_values(html: str) -> dict[str, str]:
    """Next.js flight payload fallback: \\\"name\\\":\\\"NAME ...\\\",\\\"value\\\":\\\"V\\\"."""
    out: dict[str, str] = {}
    for key, name in _SCOPES:
        m = re.search(
            r'\\"name\\":\\"' + re.escape(name) + r'\\",\\"value\\":\\"([^"\\]*)',
            html,
        )
        if m:
            out[key] = m.group(1)
    return out


def _coerce(raw: str, name: str) -> float:
    text = raw.strip()
    if text.lower() in _NO_VALUE:
        raise CboeParseError(f"{name}: value is a no-data marker ({raw!r}), not a number")
    try:
        value = float(text)
    except ValueError:
        raise CboeParseError(f"{name}: non-numeric value {raw!r}") from None
    if not 0 <= value <= _MAX_RATIO:
        raise CboeParseError(
            f"{name}: value {value} outside sanity bound [0, {_MAX_RATIO}]"
            " (likely decimal shift -- refusing to store)"
        )
    return value


def _validate_trade_date(trade_date: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date or ""):
        raise CboeParseError(f"trade_date must be ISO YYYY-MM-DD, got {trade_date!r}")
    try:
        d = date.fromisoformat(trade_date)
    except ValueError:
        raise CboeParseError(f"trade_date is not a real date: {trade_date!r}") from None
    if d.isoformat() != trade_date:
        raise CboeParseError(f"trade_date is not canonical ISO: {trade_date!r}")
    return d


def parse_cboe_daily(html: str, trade_date: str) -> CboeDaily | None:
    """Parse one CBOE daily-statistics page. Pure: no network, no DB.

    Returns None for a genuine CBOE daily page with zero ratio rows
    (weekend/holiday no-data page) -- the caller skips the write and must
    never store a dirty row. Any partial or garbled data raises
    CboeParseError (fail loud).
    """
    day = _validate_trade_date(trade_date)
    values = _table_values(html)
    if not values:
        values = _rsc_values(html)  # table absent (not yet rendered) -> RSC payload
    if not values:
        if _PAGE_MARKER in html:
            return None  # recognized CBOE daily page, no ratio data published
        raise CboeParseError(
            "zero ratio rows and no CBOE daily-statistics page marker"
            " -- site structure may have changed"
        )
    missing = [name for key, name in _SCOPES if key not in values]
    if missing:
        raise CboeParseError(
            f"partial ratio rows (missing {', '.join(missing)})"
            " -- refusing to store an incomplete day"
        )
    coerced = {key: _coerce(values[key], name) for key, name in _SCOPES}
    return CboeDaily(
        trade_date=day,
        total_put_call=coerced["total"],
        equity_put_call=coerced["equity"],
        index_put_call=coerced["index"],
    )


class CboeScraper:
    """One CBOE daily-statistics page per day, politely.

    client is injectable (tests pass a PoliteClient with MockTransport --
    no real network in tests). min_interval_s=2.0 keeps us far under any
    reasonable rate limit; the honest default User-Agent identifies us.
    """

    def __init__(self, client: PoliteClient | None = None) -> None:
        self._client = client if client is not None else PoliteClient(min_interval_s=2.0)
        self._owns_client = client is None

    def fetch_daily(self, trade_date: date) -> str:
        url = f"{CBOE_DAILY_URL}?dt={trade_date.isoformat()}"
        resp = self._client.get(url)  # HTTP errors propagate (fail loud)
        return resp.text

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _stamp(day: CboeDaily, trade_date: date) -> CboeDaily:
    day.fetched_at = day.fetched_at or datetime.now(UTC)
    day.source_url = f"{CBOE_DAILY_URL}?dt={trade_date.isoformat()}"
    return day


def putcall_series(engine, days: int) -> list[CboeDaily]:
    """Read side for the panel: the trailing `days` rows, oldest first.

    days clamps to [1, 365] (out of range clamps, never errors).
    """
    session = SessionLocal(bind=engine)
    try:
        return CboePutCallRepository(session).series(max(1, min(365, days)))
    finally:
        session.close()


def run_m5(
    engine,
    trade_date: date | None = None,
    client: PoliteClient | None = None,
) -> dict:
    """Run M5 for one day. T+1: defaults to the last trading day before
    today (ET); pass trade_date to override (backfill, manual reruns).

    No-data page -> skip the write, bump checked_at, report skipped=True.
    A garbled page raises (logged) instead of storing a wrong number.
    """
    target = trade_date or last_trading_day_before(today_et())
    scraper = CboeScraper(client)
    try:
        html = scraper.fetch_daily(target)
        try:
            day = parse_cboe_daily(html, target.isoformat())
        except CboeParseError:
            logger.exception("M5: failed to parse CBOE page for %s", target.isoformat())
            raise
    finally:
        scraper.close()
    session = SessionLocal(bind=engine)
    try:
        freshness = FreshnessRepository(session)
        if day is None:
            freshness.touch("m5")
            return {
                "skipped": True,
                "trade_date": target,
                "reason": "no ratio rows on the CBOE page (weekend/holiday)",
            }
        CboePutCallRepository(session).upsert(_stamp(day, target))
        freshness.mark("m5", target)
    finally:
        session.close()
    return {
        "skipped": False,
        "trade_date": target,
        "total_put_call": day.total_put_call,
        "equity_put_call": day.equity_put_call,
        "index_put_call": day.index_put_call,
    }


def run_backfill_m5(
    engine,
    days: int = 90,
    client: PoliteClient | None = None,
) -> dict:
    """Backfill the trailing `days` calendar days, serially.

    Non-trading days are skipped before any request; one shared scraper
    enforces the >=2s interval. A single day's failure is recorded and the
    backfill continues (upsert makes reruns idempotent).
    """
    today = today_et()
    scraper = CboeScraper(client)
    fetched = skipped = 0
    latest_fetched: date | None = None
    errors: list[dict] = []
    try:
        for back in range(days):
            d = today - timedelta(days=back)
            if not is_trading_day(d):
                skipped += 1
                continue
            try:
                html = scraper.fetch_daily(d)
                day = parse_cboe_daily(html, d.isoformat())
            except Exception as exc:  # noqa: BLE001 -- recorded, never fatal
                errors.append(
                    {"trade_date": d.isoformat(), "error": f"{type(exc).__name__}: {exc}"}
                )
                continue
            if day is None:
                skipped += 1  # holiday page with no ratio rows
                continue
            session = SessionLocal(bind=engine)
            try:
                try:
                    CboePutCallRepository(session).upsert(_stamp(day, d))
                except Exception as exc:  # noqa: BLE001 -- DB write isolated per day
                    session.rollback()
                    errors.append(
                        {
                            "trade_date": d.isoformat(),
                            "error": f"upsert {type(exc).__name__}: {exc}",
                        }
                    )
                    continue
            finally:
                session.close()
            fetched += 1
            if latest_fetched is None or d > latest_fetched:
                latest_fetched = d
    finally:
        scraper.close()
    session = SessionLocal(bind=engine)
    try:
        freshness = FreshnessRepository(session)
        if latest_fetched is not None:
            freshness.mark("m5", latest_fetched)
        else:
            freshness.touch("m5")
    finally:
        session.close()
    return {"fetched": fetched, "skipped": skipped, "errors": errors}
