export type ExposureMetric = "gex" | "vex" | "compare";

export type HeatmapViewMode = "single" | "trinity";

export type Regime = "long_gamma" | "short_gamma" | "undetermined" | string;

export interface KingDistance {
  pct: number;
  direction: "up" | "down" | "flat" | string;
  signed_pct: number;
}

export interface Levels {
  flip: number | null;
  call_wall: number | null;
  put_wall: number | null;
  king: number | null;
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

export interface PinTargets {
  method: string;
  disclaimer: string;
  primary_strike: number | null;
  primary_label: "king" | "top_magnet" | string;
  max_pain: number | null;
  pin_score: number | null;
  pin_score_breakdown: Record<string, number | null>;
  rankings: PinMagnetRow[];
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
  spot: number;
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
    data_source?: "thetadata" | "thetadata_live" | "eod" | string;
    n_strikes?: number;
    intraday_time?: string | null;
    intraday_times_available?: string[];
    quote_granularity?: string | null;
    live_refresh_seconds?: number | null;
  };
}

export interface DatesResponse {
  symbol: string;
  dates: string[];
  latest: string;
  today: string;
  default_date: string;
}
