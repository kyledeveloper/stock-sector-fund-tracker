"""Canonical data contracts shared by every layer (Pydantic v2).

This module is the single source of truth for shapes flowing through
ingest -> store -> compute -> api. Nothing else in the codebase defines
a competing record shape for these concepts.
"""

from datetime import date

from pydantic import BaseModel, Field

#: 11 GICS sector ETFs (SPDR). Contract test pins this list.
SECTOR_ETFS: tuple[str, ...] = (
    "XLK",  # Information Technology
    "XLF",  # Financials
    "XLE",  # Energy
    "XLV",  # Health Care
    "XLI",  # Industrials
    "XLP",  # Consumer Staples
    "XLY",  # Consumer Discretionary
    "XLU",  # Utilities
    "XLRE",  # Real Estate
    "XLC",  # Communication Services
    "XLB",  # Materials
)

BENCHMARK = "SPY"


class SectorFlow(BaseModel):
    """One sector ETF's net creation/redemption flow for a day (USD)."""

    as_of: date
    ticker: str
    net_flow_usd: float = Field(description="creations minus redemptions, USD")
    aum_usd: float | None = None
    source: str = ""

    @property
    def flow_to_aum(self) -> float | None:
        if self.aum_usd:
            return self.net_flow_usd / self.aum_usd
        return None


class Holding(BaseModel):
    """One ETF constituent holding (SSGA official file, T-1 basis)."""

    as_of: date  # holdings file date (T-1 vs flow date)
    etf_ticker: str
    ticker: str
    name: str = ""
    weight: float = Field(ge=0, le=1)


class ImpliedExposure(BaseModel):
    """Per-stock 'config-style capital exposure' estimate (NOT a buy flow).

    Derived as sum over sector ETFs of (sector net flow * constituent weight).
    In-kind creations involve no market buying of constituents; this number
    mixes mechanical flows and must never be labeled 主力/聪明钱.
    """

    as_of: date
    ticker: str
    implied_usd: float
    contributing_etfs: list[str] = Field(default_factory=list)
    consecutive_days: int = 1


class PriceBar(BaseModel):
    """Daily OHLCV bar (EOD source)."""

    as_of: date
    ticker: str
    close: float
    volume: int = 0


class SectorMomentum(BaseModel):
    """Sector ETF relative strength vs benchmark."""

    as_of: date
    ticker: str
    rs_20d: float  # 20-day relative return vs SPY
    rs_60d: float  # 60-day relative return vs SPY
    rrg_quadrant: str = ""  # leading/weakening/lagging/improving


class PutCallRatio(BaseModel):
    """CBOE daily put/call ratio (sentiment proxy, not a flow)."""

    as_of: date
    scope: str  # "total" | "equity" | "index"
    ratio: float


class FilingEvent(BaseModel):
    """13F-HR position change or Form 4 insider transaction (EDGAR)."""

    as_of: date
    kind: str  # "13f" | "form4"
    cik: str
    filer_name: str = ""
    ticker: str = ""
    detail: str = ""
    lag_note: str = ""  # e.g. "13F: 45-day lag"


class Freshness(BaseModel):
    """Freshness watchdog record per module."""

    module: str  # "m1".."m5"
    as_of: date | None
    checked_at: str = ""
    stale: bool = False
