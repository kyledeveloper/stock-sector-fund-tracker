"""Sector momentum / simplified RRG (M3). Phase 3.

Pure functions only. Inputs: daily bars for the 11 sector ETFs + SPY.
Outputs: 20/60-day relative strength vs SPY + RRG quadrant label
(leading / weakening / lagging / improving).
"""

from moneyflow.models import PriceBar, SectorMomentum


def sector_momentum(bars: list[PriceBar], benchmark: str = "SPY") -> list[SectorMomentum]:
    raise NotImplementedError("Phase 3")
