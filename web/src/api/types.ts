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

export interface PutCallPoint {
  date: string; // YYYY-MM-DD (ET)
  total_put_call: number;
  equity_put_call: number;
}

export interface PutCallSeries {
  data: PutCallPoint[];
  as_of: string | null;
  stale: boolean;
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

export interface ThirteenFPositionView {
  report_date: string;
  filed_at: string;
  cik: string;
  filer_name: string;
  issuer: string;
  cusip: string;
  value_usd: number;
  shares: number;
  put_call: string; // "" | "Call" | "Put"
  status: "new" | "exited" | "increased" | "decreased" | "unchanged" | "";
  value_delta_usd: number;
  prev_value_usd: number | null;
}

export interface ManagerPositionsView {
  cik: string;
  filer_name: string;
  report_date: string; // quarter end
  filed_at: string; // disclosure date (~45d lag)
  positions: ThirteenFPositionView[]; // top-N by value
  exited_count: number;
  new_count: number;
  has_previous_quarter: boolean; // false -> "new" = first quarter on file
}

export interface InsiderBuyView {
  ticker: string;
  issuer: string;
  insider: string;
  officer_title: string;
  filed_at: string;
  transaction_date: string;
  shares: number;
  price: number | null;
  value_usd: number | null;
  is_10b5_1: boolean;
  is_amendment: boolean;
  is_joint_filing: boolean;
}

export interface Freshness {
  module: "m2" | "m3" | "m4" | "m5"; // M1 cut from v1 (user D, 2026-10-01)
  as_of: string | null;
  checked_at: string;
  stale: boolean;
}
