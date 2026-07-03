"""Vendor/local alignment confidence for Terminal (resonance gate)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np

from quant_lab.config import env_var

ResonanceTier = Literal["high", "medium", "low", "unavailable"]
DivergenceSeverity = Literal["info", "warn", "critical"]

_DEFAULT_FLIP_TOL = 15.0
_DEFAULT_MAGNET_TOL_STRIKES = 1.0
_WEIGHTS = {
    "flip_align": 0.25,
    "magnet_align": 0.25,
    "pin_triangulate": 0.25,
    "wall_cage": 0.15,
    "flow_regime": 0.10,
}


def _env_float(name: str, default: float) -> float:
    raw = env_var(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class ResonanceLocal:
    spot: float
    flip: float | None
    king: float | None
    max_pain: float | None
    pin_score: float | None
    regime: str


@dataclass(frozen=True)
class ResonanceVendor:
    zero_gamma: float | None
    major_pos_oi: float | None
    major_neg_oi: float | None
    max_priors: list[tuple[float, float]]
    gex_orderflow: float | None = None


@dataclass(frozen=True)
class ResonanceDivergence:
    field: str
    local: float | None
    vendor: float | None
    delta_pts: float | None
    severity: DivergenceSeverity


@dataclass
class ResonanceReport:
    tier: ResonanceTier
    score: float
    axes: dict[str, float]
    divergences: list[ResonanceDivergence] = field(default_factory=list)
    narrative: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "score": self.score,
            "axes": self.axes,
            "divergences": [asdict(d) for d in self.divergences],
            "narrative": self.narrative,
        }


def _linear_align(delta: float, *, good: float, bad: float) -> float:
    if not np.isfinite(delta):
        return float("nan")
    if delta <= good:
        return 1.0
    if delta >= bad:
        return 0.0
    return float(1.0 - (delta - good) / (bad - good))


def _strike_delta(a: float, b: float) -> float:
    return abs(a - b)


def _max_prior_peak_strike(max_priors: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not max_priors:
        return None
    best = max(max_priors, key=lambda pair: pair[1] if np.isfinite(pair[1]) else float("-inf"))
    if not np.isfinite(best[0]):
        return None
    return float(best[0]), float(best[1])


def compute_resonance(
    local: ResonanceLocal,
    vendor: ResonanceVendor | None,
    *,
    flip_tol_pts: float | None = None,
    magnet_tol_strikes: float | None = None,
) -> ResonanceReport:
    """Score independent vendor vs local alignment (0–1) and assign confidence tier."""
    if vendor is None:
        return ResonanceReport(
            tier="unavailable",
            score=float("nan"),
            axes={},
            narrative="Vendor structure unavailable — resonance not computed.",
        )

    flip_tol = flip_tol_pts if flip_tol_pts is not None else _env_float(
        "TERMINAL_RESONANCE_FLIP_TOL", _DEFAULT_FLIP_TOL
    )
    magnet_tol = magnet_tol_strikes if magnet_tol_strikes is not None else _env_float(
        "TERMINAL_RESONANCE_MAGNET_TOL", _DEFAULT_MAGNET_TOL_STRIKES
    )

    divergences: list[ResonanceDivergence] = []
    axes: dict[str, float] = {}

    # flip_align
    if local.flip is not None and vendor.zero_gamma is not None:
        d_flip = abs(local.flip - vendor.zero_gamma)
        axes["flip_align"] = _linear_align(d_flip, good=0.0, bad=flip_tol * 2.0)
        sev: DivergenceSeverity = "info"
        if d_flip > flip_tol * 2:
            sev = "critical"
        elif d_flip > flip_tol:
            sev = "warn"
        if d_flip > flip_tol:
            divergences.append(
                ResonanceDivergence(
                    field="flip",
                    local=local.flip,
                    vendor=vendor.zero_gamma,
                    delta_pts=d_flip,
                    severity=sev,
                )
            )
    else:
        axes["flip_align"] = float("nan")

    # magnet_align
    if local.king is not None and vendor.major_pos_oi is not None:
        d_mag = _strike_delta(local.king, vendor.major_pos_oi)
        axes["magnet_align"] = _linear_align(
            d_mag, good=0.0, bad=max(magnet_tol * 3.0, 3.0)
        )
        if d_mag > magnet_tol:
            divergences.append(
                ResonanceDivergence(
                    field="magnet",
                    local=local.king,
                    vendor=vendor.major_pos_oi,
                    delta_pts=d_mag,
                    severity="warn" if d_mag <= magnet_tol * 2 else "critical",
                )
            )
    else:
        axes["magnet_align"] = float("nan")

    # pin_triangulate
    peak = _max_prior_peak_strike(vendor.max_priors)
    pin = local.pin_score if local.pin_score is not None else float("nan")
    if peak is not None and local.king is not None and np.isfinite(pin):
        peak_strike, _weight = peak
        d_pin = _strike_delta(local.king, peak_strike)
        pin_ok = pin >= 60.0 and d_pin <= max(magnet_tol, 1.0)
        axes["pin_triangulate"] = 1.0 if pin_ok else (0.5 if pin >= 40.0 else 0.0)
        if pin >= 60.0 and d_pin > magnet_tol:
            divergences.append(
                ResonanceDivergence(
                    field="pin_prior_peak",
                    local=local.king,
                    vendor=peak_strike,
                    delta_pts=d_pin,
                    severity="warn",
                )
            )
    else:
        axes["pin_triangulate"] = float("nan")

    # wall_cage
    if (
        vendor.major_neg_oi is not None
        and vendor.major_pos_oi is not None
        and np.isfinite(local.spot)
    ):
        lo = min(vendor.major_neg_oi, vendor.major_pos_oi)
        hi = max(vendor.major_neg_oi, vendor.major_pos_oi)
        inside = lo <= local.spot <= hi
        axes["wall_cage"] = 1.0 if inside else 0.0
    else:
        axes["wall_cage"] = float("nan")

    # flow_regime
    flow = vendor.gex_orderflow
    regime = local.regime
    if flow is not None and np.isfinite(flow) and regime in ("long_gamma", "short_gamma"):
        if regime == "long_gamma":
            axes["flow_regime"] = 1.0 if flow >= 0 else 0.0
        else:
            axes["flow_regime"] = 1.0 if flow <= 0 else 0.0
    else:
        axes["flow_regime"] = float("nan")

    finite_axes = {k: v for k, v in axes.items() if np.isfinite(v)}
    if not finite_axes:
        return ResonanceReport(
            tier="unavailable",
            score=float("nan"),
            axes=axes,
            divergences=divergences,
            narrative="Insufficient local/vendor fields for resonance.",
        )

    score = sum(_WEIGHTS[k] * v for k, v in finite_axes.items() if k in _WEIGHTS)
    weight_sum = sum(_WEIGHTS[k] for k in finite_axes if k in _WEIGHTS)
    score = float(score / weight_sum) if weight_sum > 0 else float("nan")

    if score >= 0.75:
        tier: ResonanceTier = "high"
    elif score >= 0.45:
        tier = "medium"
    else:
        tier = "low"

    narrative = _build_narrative(tier, divergences, local, vendor)
    return ResonanceReport(
        tier=tier,
        score=score,
        axes=axes,
        divergences=divergences,
        narrative=narrative,
    )


def _build_narrative(
    tier: ResonanceTier,
    divergences: list[ResonanceDivergence],
    local: ResonanceLocal,
    vendor: ResonanceVendor,
) -> str:
    if tier == "high":
        return "Local and GEXBot structure align — elevated confidence."
    parts: list[str] = []
    for d in divergences:
        if d.field == "flip" and d.delta_pts is not None:
            parts.append(f"flip differs by {d.delta_pts:.0f}pt")
        elif d.field == "magnet" and d.delta_pts is not None:
            parts.append(f"magnet differs by {d.delta_pts:.0f} strikes")
        elif d.field == "pin_prior_peak":
            parts.append("pin magnet vs GEXBot max_priors peak diverge")
    if (
        vendor.major_pos_oi is not None
        and local.king is not None
        and abs(local.king - vendor.major_pos_oi) <= 1.0
    ):
        parts.insert(0, "magnet agrees with GEXBot call wall")
    if not parts:
        if tier == "medium":
            return "Partial alignment — confirm before sizing up."
        return "Low alignment — treat pin/GEX as provisional."
    return "; ".join(parts).capitalize() + "."
