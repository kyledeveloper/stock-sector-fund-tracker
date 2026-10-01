/** Mirror of backend moneyflow/models.py. Keep in sync (Phase 5: generate from OpenAPI). */

export interface SectorFlow {
  as_of: string; // YYYY-MM-DD (ET)
  ticker: string;
  net_flow_usd: number;
  aum_usd: number | null;
  source: string;
}

export interface ImpliedExposure {
  as_of: string;
  ticker: string;
  implied_usd: number;
  contributing_etfs: string[];
  consecutive_days: number;
}

export interface SectorMomentum {
  as_of: string;
  ticker: string;
  rs_20d: number;
  rs_60d: number;
  rrg_quadrant: "leading" | "weakening" | "lagging" | "improving" | "";
}

export interface PutCallRatio {
  as_of: string;
  scope: "total" | "equity" | "index" | "vix" | "etp";
  ratio: number;
}

export interface FilingEvent {
  as_of: string;
  kind: "13f" | "form4";
  cik: string;
  filer_name: string;
  ticker: string;
  detail: string;
  lag_note: string;
}

export interface StockExposure {
  as_of: string; // YYYY-MM-DD (ET)
  ticker: string;
  total_weight: number; // sum of weights across sector ETFs, -0.01..~1 (small negative = futures hedge leg)
  etf_count: number;
  contributing_etfs: string[];
}

export interface Freshness {
  module: "m2" | "m3" | "m4" | "m5"; // M1 cut from v1 (user D, 2026-10-01)
  as_of: string | null;
  checked_at: string;
  stale: boolean;
}
