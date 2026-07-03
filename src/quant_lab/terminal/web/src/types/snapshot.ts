export type ExposureMetric = "gex" | "vex" | "compare";

/** 0DTE effective-OI depth for SPX intraday (API ``chain_mode``). Both compute full pin. */
export type ChainFlowMode = "pin" | "full";

export type SessionHoldStatus = "pre_market" | "awaiting_chain";

export type HeatmapViewMode = "single" | "trinity";

export type Regime = "long_gamma" | "short_gamma" | "undetermined" | string;

export interface KingDistance {
  pct: number;
  direction: "up" | "down" | "flat" | string;
  signed_pct: number;
}

export interface ModelMetadata {
  dealer_sign_assumption: string;
  dealer_sign_observed: boolean;
  interpretation_warning: string;
  vex_interpretation_warning?: string;
  pricing_inputs?: {
    model: string;
    r: number;
    q: number;
    rate_source: string;
    dividend_source: string;
  };
  time_to_expiry?: {
    mode: string;
    fallback_used: boolean;
    t_years_median: number | null;
    warning: string | null;
  };
  gamma_flip?: {
    primary_flip: number | null;
    primary_rule: string;
    all_flips: (number | null)[];
    search_radius_pct?: number;
    grid_points?: number;
    confidence: string;
  } | null;
  data_quality_warnings?: string[];
  hours_to_close?: number | null;
  live_chain_poll?: {
    from_cache?: boolean;
    stale_served?: boolean;
    chain_age_seconds?: number;
    chain_time_used?: string;
  } | null;
  live_pin_quality?: LivePinDataQuality | null;
}

export interface LivePinDataQuality {
  grade: "ok" | "degraded" | "poor" | string;
  live_follow?: boolean;
  reasons?: string[];
  chain_from_cache?: boolean;
  chain_stale_served?: boolean;
  chain_age_seconds?: number | null;
  hours_to_close?: number | null;
  n_strikes?: number;
}

export interface Levels {
  flip: number | null;
  call_wall: number | null;
  put_wall: number | null;
  king: number | null;
  magnet_strike?: number | null;
  floor: number | null;
  ceiling: number | null;
  max_pain: number | null;
  expected_move: number | null;
  expected_upper: number | null;
  expected_lower: number | null;
}

export interface HeatmapRow {
  strike: number;
  net_gex: number;
  net_gex_bn?: number;
  net_vex: number | null;
  net_vex_bn?: number | null;
  call_gex?: number;
  put_gex?: number;
  total_oi?: number;
  roc_pct: number | null;
  roc_pct_vex: number | null;
}

export interface GammaProfilePoint {
  spot: number;
  net_gex: number;
  net_gex_bn: number;
}

export interface PanelSnapshot {
  symbol: string;
  spot: number;
  regime: Regime;
  king: number;
  flip: number;
  call_wall: number;
  put_wall: number;
  pin_score: number;
  heatmap: HeatmapRow[];
  gamma_profile?: GammaProfilePoint[];
  available: boolean;
  king_distance: KingDistance | null;
  spot_change_pct: number | null;
  data_source?: "thetadata" | "thetadata_live" | "eod" | "unavailable" | string;
  data_mode?: string;
  intraday_time?: string | null;
}

export interface Metrics {
  pin_score: number | null;
  pct_gex_dte1: number | null;
  net_gex_dte1_bn: number | null;
  pct_vex_dte1: number | null;
  net_vex_dte1_bn: number | null;
  vanna_interpretation: string | null;
  pcr_oi: number | null;
  oi_conc_dte1: number | null;
  spot_vs_king_pct: number | null;
  spot_vs_flip_pct: number | null;
}

export interface StrategyHint {
  label: string;
  title: string;
  summary: string;
  structures: string[];
  confidence: string;
  sources: string[];
}

export interface Gate {
  should_trade: boolean;
  reason: string;
  base_should_trade?: boolean;
  base_reason?: string;
}

export interface VendorLevels {
  zero_gamma?: number | null;
  major_pos_oi?: number | null;
  major_neg_oi?: number | null;
  major_pos_vol?: number | null;
  major_neg_vol?: number | null;
  gex_orderflow?: number | null;
  source?: string;
  gex_method?: string;
}

export interface VendorPinLadderRow {
  strike: number;
  weight: number;
  weight_norm: number;
}

export interface VendorStreamMeta {
  source?: string;
  connection_status?: string;
  last_update_ms?: number | null;
  hubs?: string[];
  ticker?: string;
}

export interface ResonanceDivergence {
  field: string;
  local: number | null;
  vendor: number | null;
  delta_pts?: number | null;
  severity: "info" | "warn" | "critical" | string;
}

export interface ResonanceReport {
  tier: "high" | "medium" | "low" | "unavailable" | string;
  score: number | null;
  axes: Record<string, number | null>;
  divergences: ResonanceDivergence[];
  narrative: string;
}

export interface Trinity {
  score: number | null;
  direction: string;
  n_symbols: number;
  distance_pcts: Record<string, number>;
}

export interface PlaybookCheck {
  id: string;
  label: string;
  passed: boolean;
  detail: string;
  weight?: number | null;
}

export interface StructureTarget {
  level: number;
  score: number;
  distance_pts: number;
  sources: string[];
}

export interface AttractionRow {
  level: number;
  score: number;
  visual_strength: number;
  side: string;
  sources: string[];
}

export interface StructureFamilyWeights {
  gamma: number;
  vex: number;
  iv: number;
  profile?: string;
}

export interface StructureSnapshot {
  structure_version: string;
  regime: string;
  trend_state: string;
  momentum_state: string;
  momentum_score: number;
  primary_mm_target: StructureTarget | null;
  secondary_mm_target: StructureTarget | null;
  call_wall: number | null;
  put_wall: number | null;
  gamma_flip: number | null;
  execution_state: string;
  attraction_profile: AttractionRow[];
  structure_bias: number;
  family_weights?: StructureFamilyWeights | null;
  mm_reference_family_weights?: StructureFamilyWeights | null;
}

export interface PinCenterDecision {
  pin_center: number;
  center_source: string;
  center_confidence: string;
  candidates: Record<string, number>;
  size_overlay: number;
  entry_blocked: boolean;
  entry_blocked_reason: string | null;
  narrative: string;
}

export interface PlaybookExitRule {
  id: string;
  label: string;
  detail: string;
  active: boolean;
}

export interface PlaybookStructure {
  center: number;
  center_source: string;
  wing_width: number;
  long_call: number;
  long_put: number;
  summary: string;
}

export interface PinMagnetRow {
  strike: number;
  weight_pct: number;
  net_gex_bn: number;
  oi_share: number;
  dist_pct: number;
  tags: string[];
}

export interface PinClusterPayload {
  is_cluster: boolean;
  lower: number | null;
  upper: number | null;
  center: number | null;
  width: number | null;
  primary_strike: number | null;
  secondary_strike: number | null;
  strength_ratio: number | null;
  cluster_strength: "high" | "moderate" | "low" | "none" | string;
  merge_reason: string;
  spot_zone_state:
    | "inside_zone"
    | "testing_upside_exit"
    | "testing_downside_exit"
    | "above_break"
    | "below_break"
    | "unknown"
    | null;
  interpretation: string | null;
  up_break_level: number | null;
  down_break_level: number | null;
  buffer_pts: number | null;
}

export interface PinTargets {
  method: string;
  disclaimer: string;
  primary_strike: number | null;
  primary_label: "king" | "top_magnet" | string;
  max_pain: number | null;
  pin_score: number | null;
  pin_score_adjusted?: number | null;
  pin_reliability?: "high" | "moderate" | "caution" | "low" | "unknown" | string;
  pin_reliability_detail?: string | null;
  live_data_quality?: LivePinDataQuality | null;
  pin_score_breakdown: Record<string, number | null>;
  rankings: PinMagnetRow[];
  pin_cluster?: PinClusterPayload;
}

export interface PinPlaybook {
  session_phase: string;
  phase_title: string;
  phase_detail: string;
  clock_et: string;
  hours_to_close: number;
  size_multiplier: number;
  pin_multiplier: number;
  regime_multiplier: number;
  macro_multiplier: number;
  gate_multiplier: number;
  checks: PlaybookCheck[];
  structure: PlaybookStructure | null;
  exits: PlaybookExitRule[];
  trinity_score: number | null;
  trinity_direction: string | null;
  actionable: boolean;
  summary: string;
}

export interface DashboardSnapshot {
  symbol: string;
  date: string;
  /** ``hold`` = pre-open / warming up; omit or ``ready`` = normal chain. */
  availability?: "hold" | "ready" | string;
  spot: number | null;
  regime: Regime;
  levels: Levels;
  king_distance: KingDistance | null;
  spot_change_pct: number | null;
  metrics: Metrics;
  gate: Gate;
  strategy: StrategyHint;
  trinity: Trinity;
  heatmap: HeatmapRow[];
  gamma_profile?: GammaProfilePoint[];
  panels: PanelSnapshot[];
  pin_playbook?: PinPlaybook;
  pin_targets?: PinTargets;
  meta: {
    cohort: string;
    cohort_fallback?: boolean;
    gex_display_unit?: string;
    gex_formula?: string;
    dealer_sign?: string;
    data_mode: string;
    requested_date?: string | null;
    date_fallback?: boolean;
    data_source?: "thetadata" | "thetadata_live" | "eod" | string;
    n_strikes?: number;
    intraday_time?: string | null;
    intraday_times_available?: string[];
    quote_granularity?: string | null;
    live_refresh_seconds?: number | null;
    oi_mode?: "effective" | "settled" | string;
    volume_source?: "trade" | "trade_signed" | "quote_proxy" | "oi_delta" | "settled" | string;
    live_follow?: boolean;
    chain_mode?: ChainFlowMode | "gex" | string;
    session_status?: SessionHoldStatus | string;
    session_status_title?: string;
    session_status_message?: string;
    session_status_detail_en?: string;
    clock_et?: string;
    chain_time_requested?: string | null;
    trinity_live_panels?: number;
    server_pulled_at?: string | null;
    magnet_shift?: boolean;
    magnet_previous?: number | null;
    magnet_delta_pts?: number | null;
    vendor_stream?: VendorStreamMeta | null;
    vendor_levels?: VendorLevels | null;
    vendor_pin_ladder?: VendorPinLadderRow[] | null;
    resonance?: ResonanceReport | null;
    structure?: StructureSnapshot | null;
    pin_center?: PinCenterDecision | null;
    model_metadata?: ModelMetadata;
    gex_model?: string;
    risk_free_rate?: number | null;
    dividend_yield?: number | null;
    risk_free_rate_source?: string;
    dividend_yield_source?: string;
    t_years_at_calc?: number | null;
    em_source?: string;
    hours_to_close?: number | null;
    chain_clock_used?: string | null;
  };
}

export interface DatesResponse {
  symbol: string;
  dates: string[];
  latest: string;
  today: string;
  default_date: string;
}
