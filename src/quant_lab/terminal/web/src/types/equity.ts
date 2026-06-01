export type HorizonBias = "bullish" | "neutral" | "bearish";
export type EvidenceGrade = "A" | "B" | "C";

export interface HorizonVerdict {
  bias: HorizonBias;
  confidence: number;
  grade: EvidenceGrade;
  summary: string;
  drivers: string[];
  risks: string[];
}

export interface MacroEventRow {
  type: string;
  label: string;
}

export interface LayerL0 {
  adv_usd: number;
  amihud: number;
  amihud_threshold?: number;
  eligible: boolean;
  grade: EvidenceGrade;
}

export interface LayerL1 {
  macro_events: MacroEventRow[];
  earnings_window: boolean;
  vol_regime: string;
  grade: EvidenceGrade;
}

export interface LayerL2 {
  vwap: number;
  last: number;
  deviation_pct: number;
  above_vwap: boolean;
  rs_open_30m?: number;
  open_ret_pct?: number;
  benchmark_open_ret_pct?: number;
  grade: EvidenceGrade;
}

export interface LayerL3 {
  poc: number;
  vah: number;
  val: number;
  grade: EvidenceGrade;
}

export interface LayerL5 {
  rs_1d: number;
  rs_5d: number;
  rs_20d: number;
  rs_60d: number;
  rs_120d: number;
  ma20: number;
  ma50: number;
  ma200: number;
  grade: EvidenceGrade;
}

export interface LayerL6 {
  pcr_volume: number;
  pcr_oi: number;
  max_pain: number;
  n_contracts: number;
  grade: EvidenceGrade;
}

export interface EquityLayers {
  L0: LayerL0;
  L1: LayerL1;
  L2: LayerL2;
  L3: LayerL3;
  L5: LayerL5;
  L6: LayerL6 | null;
}

export interface ModuleSignal {
  bias: HorizonBias;
  score: number;
}

export type ModuleId =
  | "liquidity"
  | "context"
  | "vwap_flow"
  | "volume_profile"
  | "trend"
  | "options_flow";

export interface EquityAnalyzeResponse {
  ticker: string;
  benchmark: string;
  session_date: string;
  asof: string;
  spot: number;
  provenance: {
    daily_bars: string;
    intraday_bars: string;
    options: string;
    events: string;
  };
  layers: EquityLayers;
  modules?: Record<ModuleId, ModuleSignal>;
  horizons: {
    short: HorizonVerdict;
    mid: HorizonVerdict;
    long: HorizonVerdict;
    alignment: string;
    weakest_link: { layer: string; reason: string } | null;
    vol_regime: string;
  };
  chart: {
    interval: string;
    bars: Array<{ t: string; o: number; h: number; l: number; c: number; v: number }>;
    bars_5d?: Array<{ t: string; o: number; h: number; l: number; c: number; v: number }>;
    daily_bars?: Array<{ t: string; o: number; h: number; l: number; c: number; v: number }>;
    benchmark_daily_bars?: Array<{ t: string; o: number; h: number; l: number; c: number; v: number }>;
    overlays: {
      vwap: number;
      poc: number;
      ma20?: number;
      ma50?: number;
      ma200?: number;
    };
  };
}
