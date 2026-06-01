import type { EquityAnalyzeResponse, HorizonBias, ModuleId, ModuleSignal } from "../types/equity";

function clip(x: number): number {
  if (!Number.isFinite(x)) return 0;
  return Math.max(-1, Math.min(1, x));
}

function biasFromScore(score: number, bull = 0.12, bear = -0.12): HorizonBias {
  if (!Number.isFinite(score)) return "neutral";
  if (score > bull) return "bullish";
  if (score < bear) return "bearish";
  return "neutral";
}

function signal(bias: HorizonBias, score: number): ModuleSignal {
  return { bias, score: clip(score) };
}

const NEUTRAL: ModuleSignal = { bias: "neutral", score: 0 };

/**
 * Client fallback when API predates ``modules`` in the payload (stale server).
 * Mirrors ``quant_lab.factors.equity.layer_signals`` rules.
 */
export function deriveModuleSignals(data: EquityAnalyzeResponse): Record<ModuleId, ModuleSignal> {
  const l0 = data.layers?.L0;
  const l1 = data.layers?.L1;
  const l2 = data.layers?.L2;
  const l3 = data.layers?.L3;
  const l5 = data.layers?.L5;
  const l6 = data.layers?.L6;
  const spot = data.spot;

  if (!l0 || !l1 || !l2 || !l3 || !l5) {
    return {
      liquidity: NEUTRAL,
      context: NEUTRAL,
      vwap_flow: NEUTRAL,
      volume_profile: NEUTRAL,
      trend: NEUTRAL,
      options_flow: NEUTRAL,
    };
  }

  let liqScore = 0;
  if (!l0.eligible || (Number.isFinite(l0.adv_usd) && l0.adv_usd < 5_000_000)) {
    liqScore = -0.35;
  } else {
    const amihudHigh = Number.isFinite(l0.amihud_threshold) ? l0.amihud_threshold! : 1.0;
    if (Number.isFinite(l0.amihud) && l0.amihud > amihudHigh) {
      liqScore = -0.2;
    } else if (Number.isFinite(l0.adv_usd) && l0.adv_usd >= 20_000_000) {
      liqScore = 0.08;
    }
  }

  let ctxScore = 0;
  if (l1.earnings_window) ctxScore -= 0.35;
  if (l1.vol_regime === "elevated" || l1.vol_regime === "high") ctxScore -= 0.15;
  else if (l1.vol_regime === "low") ctxScore += 0.05;
  if (l1.macro_events?.length) ctxScore -= 0.08;

  let vwapScore = 0;
  if (Number.isFinite(l2.deviation_pct)) {
    vwapScore += Math.max(-1, Math.min(1, l2.deviation_pct / 1.2)) * 0.65;
  }

  let vpScore = 0;
  const last = l2.last;
  if (Number.isFinite(l3.poc) && Number.isFinite(last) && l3.poc !== 0) {
    vpScore += Math.max(-1, Math.min(1, ((last - l3.poc) / l3.poc) * 100 / 1.5)) * 0.55;
  }
  if (Number.isFinite(l3.vah) && Number.isFinite(l3.val) && Number.isFinite(last)) {
    if (last >= l3.vah) vpScore += 0.12;
    else if (last <= l3.val) vpScore -= 0.12;
  }

  let trendScore = 0;
  if (Number.isFinite(l5.rs_20d)) {
    trendScore += Math.max(-1, Math.min(1, l5.rs_20d / 5)) * 0.45;
  }
  if (Number.isFinite(l5.ma20) && Number.isFinite(l5.ma50)) {
    trendScore += l5.ma20 >= l5.ma50 ? 0.18 : -0.18;
  }
  if (Number.isFinite(l5.ma200) && Number.isFinite(spot)) {
    trendScore += spot >= l5.ma200 ? 0.12 : -0.12;
  }

  let optScore = 0;
  if (l6) {
    if (Number.isFinite(l6.pcr_volume)) {
      if (l6.pcr_volume < 0.85) optScore += 0.22;
      else if (l6.pcr_volume > 1.15) optScore -= 0.22;
    }
    if (Number.isFinite(l6.max_pain) && Number.isFinite(spot) && spot !== 0) {
      optScore += Math.max(-0.2, Math.min(0.2, ((spot - l6.max_pain) / spot) * 100 / 5));
    }
  }

  return {
    liquidity: signal(biasFromScore(liqScore, 0.05, -0.15), liqScore),
    context: signal(biasFromScore(ctxScore, 0.08, -0.12), ctxScore),
    vwap_flow: signal(biasFromScore(vwapScore), vwapScore),
    volume_profile: signal(biasFromScore(vpScore), vpScore),
    trend: signal(biasFromScore(trendScore), trendScore),
    options_flow: signal(biasFromScore(optScore), optScore),
  };
}

export function resolveModuleSignals(data: EquityAnalyzeResponse): Record<ModuleId, ModuleSignal> {
  const raw = data.modules;
  if (raw && raw.vwap_flow?.bias && raw.volume_profile?.bias) {
    return raw;
  }
  return deriveModuleSignals(data);
}
