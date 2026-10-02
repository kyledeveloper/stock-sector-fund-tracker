"""Canonical data contracts shared by every layer (Pydantic v2).

This module is the single source of truth for shapes flowing through
ingest -> store -> compute -> api. Nothing else in the codebase defines
a competing record shape for these concepts.
"""

from datetime import UTC, date, datetime

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
    """One sector ETF's net creation/redemption flow for a day (USD).

    v2 concept: M1 was cut from v1 (user decision 2026-10-01), so nothing
    produces this model yet. Kept as the contract for a future flow source.
    """

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
    # Real SSGA files carry small negative weights for short futures hedges
    # (e.g. XLF "XAF FINANCIAL DEC26" at -0.01% on 2026-10-01). Allow down to
    # -1%; anything beyond is a data error and fails loudly.
    weight: float = Field(ge=-0.01, le=1)


class ImpliedExposure(BaseModel):
    """Per-stock 'config-style capital exposure' estimate (NOT a buy flow).

    Derived as sum over sector ETFs of (sector net flow * constituent weight).
    In-kind creations involve no market buying of constituents; this number
    mixes mechanical flows and must never be labeled 主力/聪明钱.

    v2 concept: M1 was cut from v1 (user decision 2026-10-01), so nothing
    produces this model yet. v1 uses StockExposure (holdings snapshot) instead.
    """

    as_of: date
    ticker: str
    implied_usd: float
    contributing_etfs: list[str] = Field(default_factory=list)
    consecutive_days: int = 1


class StockExposure(BaseModel):
    """Per-stock cross-sector weight snapshot (M2, v1). NOT a fund flow.

    total_weight = sum of the stock's weights across the 11 sector ETFs
    (a stock can sit in several, e.g. GOOGL in XLC and XLY).
    A holdings snapshot only: day-over-day weight changes are mostly price
    moves, never fund flows. Panel copy must say so.
    """

    as_of: date
    ticker: str
    # May be slightly negative: a ticker held only as a short futures hedge
    # (e.g. IXAZ6 at -0.01% in XLF) sums to a negative total. Same bound as Holding.
    total_weight: float = Field(ge=-0.01, description="sum of weights, ~0..1")
    etf_count: int = Field(ge=1, default=1)
    contributing_etfs: list[str] = Field(default_factory=list)


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
    scope: str  # "total" | "equity" | "index" | "vix" | "etp" (CBOE publishes all five)
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


class ThirteenFHolding(BaseModel):
    """One parsed 13F-HR information-table row (a quarter's position)."""

    report_date: date  # quarter end
    filed_at: date  # when the 13F-HR was filed
    cik: str  # 10-digit, zero-padded
    filer_name: str = ""
    issuer: str  # nameOfIssuer, e.g. "PALANTIR TECHNOLOGIES INC"
    cusip: str
    title_of_class: str = ""
    value_usd: float  # 13F reports whole dollars
    shares: int
    put_call: str = ""  # "" = common stock; "Call"/"Put" = option leg


class ThirteenFFilingRef(BaseModel):
    """Pointer to the newest 13F-HR in a submissions JSON."""

    accession_number: str  # with dashes, e.g. 0001649339-25-000007
    filing_date: date
    report_date: date


class ThirteenFPositionView(BaseModel):
    """Latest-quarter 13F position + QoQ status (read model for the panel)."""

    report_date: date
    filed_at: date
    cik: str
    filer_name: str = ""
    issuer: str
    cusip: str
    value_usd: float  # 0 for exited positions
    shares: int  # 0 for exited positions
    put_call: str = ""
    status: str = ""  # new|exited|increased|decreased|unchanged
    value_delta_usd: float = 0.0
    prev_value_usd: float | None = None


class InsiderTransaction(BaseModel):
    """One Form 4 non-derivative transaction."""

    ordinal: int = 0  # 0-based row index within the filing (B1: part of the PK)
    transaction_date: date
    transaction_code: str  # P = open-market purchase, S = sale, ...
    acquired_disposed: str  # "A" | "D"
    shares: int
    price: float | None = None
    value_usd: float | None = None  # shares * price
    side: str = ""  # "buy" | "sell" (from acquired/disposed)
    is_open_market_buy: bool = False  # code P + acquired
    is_10b5_1: bool = False


class Form4Filing(BaseModel):
    """Parsed Form 4 ownership document (one filing)."""

    ticker: str  # issuerTradingSymbol -- Form 4 HAS the ticker (unlike 13F)
    issuer: str = ""
    issuer_cik: str = ""
    insider: str = ""
    insider_cik: str = ""
    is_joint_filing: bool = False  # M3: >1 reportingOwner; insider holds all names
    officer_title: str = ""  # primary owner's title
    is_officer: bool = False  # OR across joint filers (M3: no silent exclusion)
    is_director: bool = False  # OR across joint filers
    is_ten_percent_owner: bool = False
    filed_at: date
    accession_number: str = ""
    form_type: str = "4"  # "4" | "4/A" (M2: amendments flagged, not auto-superseded)
    transactions: list[InsiderTransaction] = []


class InsiderBuyView(BaseModel):
    """Officer/director open-market buy for the Form 4 panel (read model)."""

    ticker: str
    issuer: str = ""
    insider: str = ""
    officer_title: str = ""
    filed_at: date
    transaction_date: date
    shares: int
    price: float | None = None
    value_usd: float | None = None
    is_10b5_1: bool = False
    is_amendment: bool = False  # M2: from a 4/A filing; corrected values may
    # appear as separate rows (v1 flags, does not auto-supersede)
    is_joint_filing: bool = False  # M3


class ManagerPositionsView(BaseModel):
    """One manager's latest 13F quarter for the panel (read model)."""

    cik: str
    filer_name: str = ""
    report_date: date
    filed_at: date
    positions: list[ThirteenFPositionView]  # top-N current positions by value
    exited_count: int = 0
    new_count: int = 0
    has_previous_quarter: bool = False  # M4: False -> "new" badges mean
    # "first quarter on file", not "newly opened this quarter"


# M4 13F watchlist: (display name, CIK). Approved by the user 2026-10-01
# (12 managers). CIKs cross-verified multi-source; verify_filer_name
# re-checks each CIK's registered name against EDGAR at runtime --
# a wrong CIK fails loud instead of attributing holdings to the wrong manager.
M4_WATCHLIST: tuple[tuple[str, str], ...] = (
    ("Berkshire Hathaway", "1067983"),
    ("Pershing Square", "1336528"),
    ("Duquesne Family Office", "1536411"),
    ("Baupost Group", "1061768"),
    ("Third Point", "1040273"),
    ("Appaloosa", "1656456"),
    ("Tiger Global", "1167483"),
    ("Scion Asset Management", "1649339"),
    ("Himalaya Capital", "1709323"),
    ("Viking Global", "1103804"),
    ("Soros Fund Management", "1029160"),
    ("Elliott Investment Management", "1791786"),
)


class Freshness(BaseModel):
    """Freshness watchdog record per module.

    checked_at is a datetime server-side; it serializes to an ISO-8601
    string over the API, which is what web/src/api/types.ts mirrors.
    """

    module: str  # "m2".."m5" (M1 cut from v1)
    as_of: date | None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stale: bool = False
