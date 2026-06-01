"""Per-module bullish / neutral / bearish signals for equity research UI."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np

from quant_lab.factors.equity.liquidity_thresholds import liquidity_module_score
from quant_lab.factors.equity.ma_structure import MaStructure
from quant_lab.factors.equity.options_overlay import OptionsOverlay
from quant_lab.factors.equity.relative_strength import RelativeStrength
from quant_lab.factors.equity.vol_regime import VolRegimeResult
from quant_lab.factors.equity.volume_profile import VolumeProfile
from quant_lab.factors.equity.vwap import VwapMetrics

Bias = Literal["bullish", "neutral", "bearish"]


def _clip_score(x: float) -> float:
    if not np.isfinite(x):
        return 0.0
    return float(max(-1.0, min(1.0, x)))


def _bias_from_score(score: float, *, bull: float = 0.12, bear: float = -0.12) -> Bias:
    if not np.isfinite(score):
        return "neutral"
    if score > bull:
        return "bullish"
    if score < bear:
        return "bearish"
    return "neutral"


def _signal(bias: Bias, score: float) -> dict[str, Any]:
    return {"bias": bias, "score": round(_clip_score(score), 3)}


def liquidity_signal(
    *,
    eligible: bool,
    adv_usd: float,
    amihud: float,
    amihud_threshold: float = float("nan"),
) -> dict[str, Any]:
    score = liquidity_module_score(
        eligible=eligible,
        adv_usd=adv_usd,
        amihud=amihud,
        amihud_threshold=amihud_threshold,
    )
    return _signal(_bias_from_score(score, bull=0.05, bear=-0.15), score)


def context_signal(
    *,
    vol: VolRegimeResult,
    earnings_window: bool,
    macro_count: int,
) -> dict[str, Any]:
    score = 0.0
    if earnings_window:
        score -= 0.35
    if vol.regime == "elevated":
        score -= 0.15
    elif vol.regime == "low":
        score += 0.05
    if macro_count > 0:
        score -= 0.08
    return _signal(_bias_from_score(score, bull=0.08, bear=-0.12), score)


def vwap_flow_signal(vwap: VwapMetrics) -> dict[str, Any]:
    score = 0.0
    if np.isfinite(vwap.deviation_pct):
        score += np.clip(vwap.deviation_pct / 1.2, -1.0, 1.0) * 0.65
    return _signal(_bias_from_score(score), score)


def volume_profile_signal(*, profile: VolumeProfile, last_close: float) -> dict[str, Any]:
    score = 0.0
    if np.isfinite(profile.poc) and np.isfinite(last_close) and profile.poc != 0:
        poc_dist = (last_close - profile.poc) / profile.poc * 100.0
        score += np.clip(poc_dist / 1.5, -1.0, 1.0) * 0.55
    if np.isfinite(profile.vah) and np.isfinite(profile.val) and np.isfinite(last_close):
        if last_close >= profile.vah:
            score += 0.12
        elif last_close <= profile.val:
            score -= 0.12
    return _signal(_bias_from_score(score), score)


def trend_signal(*, rs: RelativeStrength, ma: MaStructure, spot: float) -> dict[str, Any]:
    score = 0.0
    if np.isfinite(rs.rs_20d):
        score += np.clip(rs.rs_20d / 5.0, -1.0, 1.0) * 0.45
    if ma.ma20_above_ma50:
        score += 0.18
    else:
        score -= 0.18
    if np.isfinite(ma.ma200) and np.isfinite(spot):
        score += 0.12 if spot >= ma.ma200 else -0.12
    return _signal(_bias_from_score(score), score)


def options_flow_signal(options: OptionsOverlay | None, *, spot: float) -> dict[str, Any]:
    if options is None:
        return _signal("neutral", 0.0)
    score = 0.0
    if np.isfinite(options.pcr_volume):
        if options.pcr_volume < 0.85:
            score += 0.22
        elif options.pcr_volume > 1.15:
            score -= 0.22
    if np.isfinite(options.max_pain) and np.isfinite(spot) and spot != 0:
        mp_dist = (spot - options.max_pain) / spot * 100.0
        score += np.clip(mp_dist / 5.0, -0.2, 0.2)
    return _signal(_bias_from_score(score), score)


def compute_module_signals(
    *,
    vwap: VwapMetrics,
    profile: VolumeProfile,
    rs: RelativeStrength,
    ma: MaStructure,
    vol: VolRegimeResult,
    options: OptionsOverlay | None,
    spot: float,
    eligible: bool,
    adv_usd: float,
    amihud: float,
    earnings_window: bool,
    macro_count: int,
    amihud_threshold: float = float("nan"),
) -> dict[str, dict[str, Any]]:
    """Return UI-ready module bias map keyed by module id."""
    return {
        "liquidity": liquidity_signal(
            eligible=eligible,
            adv_usd=adv_usd,
            amihud=amihud,
            amihud_threshold=amihud_threshold,
        ),
        "context": context_signal(vol=vol, earnings_window=earnings_window, macro_count=macro_count),
        "vwap_flow": vwap_flow_signal(vwap),
        "volume_profile": volume_profile_signal(profile=profile, last_close=vwap.last_close),
        "trend": trend_signal(rs=rs, ma=ma, spot=spot),
        "options_flow": options_flow_signal(options, spot=spot),
    }
