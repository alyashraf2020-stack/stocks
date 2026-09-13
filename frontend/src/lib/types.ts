export interface Stock {
  ticker: string;
  arabic_name: string;
  english_name: string;
  isin?: string | null;
  sector: string;
  listing_status: string;
  indices: string[];
  source: string;
  source_updated_at: string;
  latest_close?: number | null;
  latest_session_date?: string | null;
  expected_session_date?: string | null;
  sessions_behind?: number | null;
  freshness?: string | null;
  actual_provider?: string | null;
  analysis_available?: boolean;
  analytical_bars_count?: number | null;
  current_analysis_eligible?: boolean | null;
}

export interface StockListResponse {
  total: number;
  provenance_source: string;
  provenance_updated_at: string;
  items: Stock[];
}

export interface CandleBar {
  session_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  actual_provider: string;
  validation_status: string;
  sma_20?: number | null;
  sma_50?: number | null;
  rsi_14?: number | null;
  macd_line?: number | null;
  macd_signal?: number | null;
  macd_hist?: number | null;
  bb_upper?: number | null;
  bb_middle?: number | null;
  bb_lower?: number | null;
  bb_bandwidth?: number | null;
  atr_14?: number | null;
}

export interface ChartData {
  ticker: string;
  range_selected: string;
  total_bars: number;
  expected_latest_session: string;
  latest_available_session?: string | null;
  latest_close?: number | null;
  sessions_behind?: number | null;
  freshness: string;
  freshness_ar: string;
  actual_provider?: string | null;
  bars: CandleBar[];
}

export interface TradePlan {
  entry_zone_min?: number | null;
  entry_zone_max?: number | null;
  planning_entry?: number | null;
  stop_loss?: number | null;
  r_unit?: number | null;
  target_1?: number | null;
  target_2?: number | null;
  target_3?: number | null;
  support_level?: number | null;
  resistance_level?: number | null;
  entry_basis?: string | null;
  stop_basis?: string | null;
  factor_score?: number | null;
  analysis_strength?: string | null;
  factor_breakdown?: Record<string, number> | null;
  plan_status?: string | null;
  new_entry_allowed?: boolean | null;
}

export interface PositionSizing {
  capital: number;
  planning_entry: number;
  stop_loss: number;
  risk_per_share: number;
  max_risk_allowed_egp: number;
  max_allocation_allowed_egp: number;
  shares_by_risk: number;
  shares_by_allocation: number;
  suggested_shares: number;
  position_value_egp: number;
  max_expected_loss_egp: number;
  actual_risk_pct: number;
  actual_allocation_pct: number;
}

export interface LiveAnalysisResult {
  ticker: string;
  current_price: number;
  decision: string;
  decision_ar: string;
  badge_color: string;
  actionable_new_trade: boolean;
  current_analysis_eligible: boolean;
  reason_ar: string;
  owns_stock?: boolean | null;
  buy_price?: number | null;
  shares_owned?: number | null;
  expected_latest_session?: string | null;
  latest_available_session?: string | null;
  latest_close?: number | null;
  sessions_behind?: number | null;
  freshness_ar?: string | null;
  actual_provider?: string | null;
  analytical_bars_count?: number | null;
  plan_status?: string | null;
  new_entry_allowed?: boolean | null;
  status: string;
  trade_plan?: TradePlan | null;
  previous_plan?: TradePlan | null;
  position_sizing?: PositionSizing | null;
}

export interface MarketStatus {
  is_open_now: boolean;
  current_cairo_time: string;
  expected_latest_completed_session: string;
  total_listed_equities: number;
  active_equities_count: number;
  suspended_equities_count: number;
  provenance_source: string;
  provenance_updated_at: string;
}