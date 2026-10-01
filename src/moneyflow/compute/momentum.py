"""Sector momentum vs SPY + simplified RRG quadrant (M3).

Pure functions only: no I/O, no clock, no database.

Definitions (documented here, not standard RRG):
- rs_Nd: N-day *excess* return vs the benchmark, as a fraction:
      (P_t / P_{t-N} - 1) - (SPY_t / SPY_{t-N} - 1)
  Positive means the sector outperformed SPY over the window.
- Simplified RRG quadrant from (rs_60d, rs_20d):
      leading    rs_60d > 0 and rs_20d > 0
      weakening  rs_60d > 0 and rs_20d <= 0
      lagging    rs_60d <= 0 and rs_20d <= 0
      improving  rs_60d <= 0 and rs_20d > 0

Each ticker needs at least 61 closes (t and t-60); fewer raises
ValueError naming the ticker. The batch-level unanimity gate
(all tickers sharing one latest bar date) lives in services/m3,
mirroring red-team B1 from Phase 1.
"""

from __future__ import annotations

from moneyflow.models import BENCHMARK, PriceBar, SectorMomentum

_MIN_BARS = 61  # need t and t-60


def _excess_return(
    by_date: dict, bench_dates: list, bench: dict, window: int, ticker: str
) -> float:
    """Excess return over `window` trading days, aligned on benchmark dates.

    Missing ticker bars on benchmark dates fail loud: silently shifting
    the window would corrupt the momentum signal.
    """
    d_now, d_then = bench_dates[-1], bench_dates[-1 - window]
    for d in (d_now, d_then):
        if d not in by_date:
            raise ValueError(f"M3: {ticker} missing bar for {d.isoformat()}")
    return (by_date[d_now] / by_date[d_then] - 1) - (bench[d_now] / bench[d_then] - 1)


def _quadrant(rs_60d: float, rs_20d: float) -> str:
    if rs_60d > 0:
        return "leading" if rs_20d > 0 else "weakening"
    return "improving" if rs_20d > 0 else "lagging"


def sector_momentum(
    bars_by_ticker: dict[str, list[PriceBar]],
    benchmark: str = BENCHMARK,
) -> list[SectorMomentum]:
    """Compute 20/60-day excess return vs benchmark + RRG quadrant.

    Output is sorted by rs_20d descending (rank-ready for the panel).
    The benchmark itself is excluded from the output.
    """
    if benchmark not in bars_by_ticker:
        raise ValueError(f"M3: benchmark {benchmark} missing from batch")
    bench_bars = sorted(bars_by_ticker[benchmark], key=lambda b: b.as_of)
    if len(bench_bars) < _MIN_BARS:
        raise ValueError(f"M3: {benchmark} has {len(bench_bars)} bars, need {_MIN_BARS}")
    bench_by_date = {b.as_of: b.close for b in bench_bars}
    bench_dates = [b.as_of for b in bench_bars]
    as_of = bench_dates[-1]

    out: list[SectorMomentum] = []
    for ticker in sorted(bars_by_ticker):
        if ticker == benchmark:
            continue
        bars = sorted(bars_by_ticker[ticker], key=lambda b: b.as_of)
        if len(bars) < _MIN_BARS:
            raise ValueError(f"M3: {ticker} has {len(bars)} bars, need {_MIN_BARS}")
        by_date = {b.as_of: b.close for b in bars}
        rs_20d = _excess_return(by_date, bench_dates, bench_by_date, 20, ticker)
        rs_60d = _excess_return(by_date, bench_dates, bench_by_date, 60, ticker)
        out.append(
            SectorMomentum(
                as_of=as_of,
                ticker=ticker,
                rs_20d=rs_20d,
                rs_60d=rs_60d,
                rrg_quadrant=_quadrant(rs_60d, rs_20d),
            )
        )
    out.sort(key=lambda m: m.rs_20d, reverse=True)
    return out
