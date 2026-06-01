"""Multi-horizon research verdict synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from quant_lab.factors.equity.evidence_grades import (
    grade_l2,
    grade_long,
    grade_mid,
)
from quant_lab.factors.equity.liquidity_thresholds import AMIHUD_HIGH, is_execution_risk
from quant_lab.factors.equity.ma_structure import MaStructure
from quant_lab.factors.equity.options_overlay import OptionsOverlay
from quant_lab.factors.equity.relative_strength import RelativeStrength
from quant_lab.factors.equity.session_structure import OpeningSegment
from quant_lab.factors.equity.vol_regime import VolRegimeResult
from quant_lab.factors.equity.volume_profile import VolumeProfile
from quant_lab.factors.equity.vwap import VwapMetrics

Bias = Literal["bullish", "neutral", "bearish"]
Grade = Literal["A", "B", "C"]


@dataclass(frozen=True)
class HorizonVerdict:
    bias: Bias
    confidence: float
    grade: Grade
    summary: str
    drivers: tuple[str, ...]
    risks: tuple[str, ...]


def _clip_conf(x: float) -> float:
    if not np.isfinite(x):
        return 0.35
    return float(max(0.05, min(0.95, x)))


def _bias_from_score(score: float) -> Bias:
    if not np.isfinite(score):
        return "neutral"
    if score > 0.12:
        return "bullish"
    if score < -0.12:
        return "bearish"
    return "neutral"


def _short_verdict(
    vwap: VwapMetrics,
    profile: VolumeProfile,
    *,
    intraday_grade: Grade,
    opening: OpeningSegment | None,
) -> HorizonVerdict:
    score = 0.0
    drivers: list[str] = []
    risks: list[str] = []

    if np.isfinite(vwap.deviation_pct):
        score += np.clip(vwap.deviation_pct / 1.5, -1.0, 1.0) * 0.5
        drivers.append(f"vs VWAP {vwap.deviation_pct:+.2f}%")
    if np.isfinite(profile.poc) and np.isfinite(vwap.last_close):
        poc_dist = (vwap.last_close - profile.poc) / profile.poc * 100.0
        score += np.clip(poc_dist / 2.0, -0.3, 0.3)
        drivers.append(f"POC {profile.poc:.2f}")

    if opening is not None and np.isfinite(opening.rs_open_30m):
        score += np.clip(opening.rs_open_30m / 0.75, -1.0, 1.0) * 0.25
        drivers.append(f"Open 30m RS vs SPY {opening.rs_open_30m:+.2f}%")

    if intraday_grade == "C":
        risks.append("Intraday data delayed (yfinance fallback)")

    bias = _bias_from_score(score)
    conf = _clip_conf(0.45 + abs(score) * 0.35)
    summary = (
        f"Session structure {'above' if vwap.above_vwap else 'below'} VWAP; "
        f"bias {bias} on micro structure."
    )
    return HorizonVerdict(
        bias=bias,
        confidence=conf,
        grade=intraday_grade,
        summary=summary,
        drivers=tuple(drivers),
        risks=tuple(risks),
    )


def _mid_verdict(
    rs: RelativeStrength,
    ma: MaStructure,
    options: OptionsOverlay | None,
    *,
    earnings_risk: bool,
    macro_labels: tuple[str, ...],
    mid_grade: Grade,
) -> HorizonVerdict:
    score = 0.0
    drivers: list[str] = []
    risks: list[str] = []

    if np.isfinite(rs.rs_20d):
        score += np.clip(rs.rs_20d / 5.0, -1.0, 1.0) * 0.45
        drivers.append(f"RS vs SPY 20d {rs.rs_20d:+.2f}%")
    if ma.ma20_above_ma50:
        score += 0.15
        drivers.append("MA20 > MA50")
    else:
        score -= 0.15
        drivers.append("MA20 < MA50")
    if options is not None and np.isfinite(options.pcr_volume):
        if options.pcr_volume < 0.85:
            score += 0.1
            drivers.append(f"PCR vol {options.pcr_volume:.2f} (call-heavy)")
        elif options.pcr_volume > 1.15:
            score -= 0.1
            drivers.append(f"PCR vol {options.pcr_volume:.2f} (put-heavy)")

    if earnings_risk:
        risks.append("Earnings window — cap confidence")
        score *= 0.6
    for label in macro_labels:
        risks.append(f"Macro event: {label}")

    bias = _bias_from_score(score)
    conf = _clip_conf(0.5 + abs(score) * 0.3)
    if earnings_risk:
        conf = min(conf, 0.55)
    if macro_labels:
        conf = min(conf, 0.6)
    return HorizonVerdict(
        bias=bias,
        confidence=conf,
        grade=mid_grade,
        summary=f"Mid-horizon drift vs SPY: {bias}.",
        drivers=tuple(drivers),
        risks=tuple(risks),
    )


def _long_verdict(rs: RelativeStrength, ma: MaStructure, *, long_grade: Grade) -> HorizonVerdict:
    score = 0.0
    drivers: list[str] = []
    rs_long = rs.rs_120d if np.isfinite(rs.rs_120d) else rs.rs_60d
    if np.isfinite(rs_long):
        score += np.clip(rs_long / 8.0, -1.0, 1.0) * 0.5
        drivers.append(f"RS vs SPY long {rs_long:+.2f}%")
    if ma.above_ma200:
        score += 0.2
        drivers.append("Price above MA200")
    else:
        score -= 0.2
        drivers.append("Price below MA200")

    bias = _bias_from_score(score)
    conf = _clip_conf(0.55 + abs(score) * 0.25)
    return HorizonVerdict(
        bias=bias,
        confidence=conf,
        grade=long_grade,
        summary=f"Long-horizon trend context: {bias}.",
        drivers=tuple(drivers),
        risks=(),
    )


def _alignment(short: Bias, mid: Bias, long: Bias) -> str:
    biases = {short, mid, long}
    if len(biases) == 1:
        return "aligned"
    if "neutral" in biases and len(biases) <= 2:
        return "mixed"
    if short != long:
        return "conflicting"
    return "mixed"


def _verdict_to_dict(v: HorizonVerdict) -> dict[str, Any]:
    return {
        "bias": v.bias,
        "confidence": round(v.confidence, 3),
        "grade": v.grade,
        "summary": v.summary,
        "drivers": list(v.drivers),
        "risks": list(v.risks),
    }


def synthesize_horizons(
    *,
    vwap: VwapMetrics,
    profile: VolumeProfile,
    rs: RelativeStrength,
    ma: MaStructure,
    vol: VolRegimeResult,
    options: OptionsOverlay | None,
    intraday_source: str,
    intraday_bars: int,
    adv: float,
    amihud: float,
    earnings_risk: bool,
    macro_labels: tuple[str, ...],
    opening: OpeningSegment | None,
    n_daily: int,
) -> dict[str, Any]:
    intraday_grade = grade_l2(intraday_source=intraday_source, n_bars=intraday_bars)
    mid_grade = grade_mid(
        earnings_risk=earnings_risk,
        options_available=options is not None,
        n_daily=n_daily,
    )
    rs_long = rs.rs_120d if np.isfinite(rs.rs_120d) else rs.rs_60d
    long_grade = grade_long(n_daily=n_daily, rs_long_finite=np.isfinite(rs_long))

    short = _short_verdict(vwap, profile, intraday_grade=intraday_grade, opening=opening)
    mid = _mid_verdict(
        rs,
        ma,
        options,
        earnings_risk=earnings_risk,
        macro_labels=macro_labels,
        mid_grade=mid_grade,
    )
    long = _long_verdict(rs, ma, long_grade=long_grade)

    weakest: dict[str, str] | None = None
    if is_execution_risk(adv):
        weakest = {"layer": "L0", "reason": "Low dollar volume — execution risk"}
    elif np.isfinite(amihud) and amihud > AMIHUD_HIGH:
        weakest = {"layer": "L0", "reason": "High Amihud illiquidity"}
    elif intraday_grade == "C":
        weakest = {"layer": "L2", "reason": "Delayed intraday bars"}
    elif options is None:
        weakest = {"layer": "L6", "reason": "Options overlay unavailable"}

    return {
        "short": _verdict_to_dict(short),
        "mid": _verdict_to_dict(mid),
        "long": _verdict_to_dict(long),
        "alignment": _alignment(short.bias, mid.bias, long.bias),
        "weakest_link": weakest,
        "vol_regime": vol.regime,
    }
