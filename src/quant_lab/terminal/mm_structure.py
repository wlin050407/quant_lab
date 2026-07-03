"""MM-style structure map from GEXBot classic + orderflow (Pin Center Fusion P0)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np

from quant_lab.config import env_var
from quant_lab.terminal.structure_history import trend_pct, trend_summary

StructureRegime = Literal[
    "positive_gamma",
    "negative_gamma",
    "unstable_near_zero_gamma",
    "transition",
]
MomentumState = Literal[
    "up_momentum",
    "down_momentum",
    "mixed_momentum",
    "flat_momentum",
]
ExecutionState = Literal[
    "at_mm_target_pin_or_take_profit",
    "dynamic_conflict_pin_wait",
    "macro_target_watch",
    "transition",
]

_STRIKE_GRID = 5.0
_ZERO_GAMMA_BAND = 5.0
_GEX_SCALE = 1_500_000.0
_DEX_SCALE = 2_500.0
_FLOW_SCALE = 350.0
_VEX_STRENGTH_CAP = 1.2
_IV_STRENGTH_CAP = 1.5

# MM reference app §6 uses family_mix weights ~45/30/25 (gamma/vex/iv).
# Pin Play D1 (fly center) is gamma-pin dominated; vanna informs vol–spot flow (D2/D4),
# not strike selection — keep vanna materially below MM defaults until V1/V2 replay.
MM_REFERENCE_FAMILY_WEIGHTS: dict[str, float] = {
    "gamma": 0.45,
    "vex": 0.30,
    "iv": 0.25,
    "profile": "mm_reference",
}
PIN_PLAY_FAMILY_WEIGHTS: dict[str, float] = {
    "gamma": 0.72,
    "vex": 0.12,
    "iv": 0.16,
    "profile": "pin_play_p0",
}


@dataclass(frozen=True)
class FamilyWeights:
    gamma: float
    vex: float
    iv: float
    profile: str = "pin_play_p0"

    def normalized(self) -> FamilyWeights:
        total = self.gamma + self.vex + self.iv
        if total <= 0:
            ref = PIN_PLAY_FAMILY_WEIGHTS
            return FamilyWeights(ref["gamma"], ref["vex"], ref["iv"], self.profile)
        return FamilyWeights(
            self.gamma / total,
            self.vex / total,
            self.iv / total,
            self.profile,
        )

    def to_dict(self) -> dict[str, float | str]:
        return {
            "gamma": self.gamma,
            "vex": self.vex,
            "iv": self.iv,
            "profile": self.profile,
        }


def _env_float(name: str, default: float) -> float:
    raw = env_var(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def family_weights_from_env() -> FamilyWeights:
    """Load family mix weights (env-overridable). Defaults favor gamma for Pin Play."""
    return FamilyWeights(
        gamma=_env_float("MM_FAMILY_GAMMA_W", PIN_PLAY_FAMILY_WEIGHTS["gamma"]),
        vex=_env_float("MM_FAMILY_VEX_W", PIN_PLAY_FAMILY_WEIGHTS["vex"]),
        iv=_env_float("MM_FAMILY_IV_W", PIN_PLAY_FAMILY_WEIGHTS["iv"]),
        profile="env",
    ).normalized()


@dataclass(frozen=True)
class StructureTarget:
    level: float
    score: float
    distance_pts: float
    sources: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AttractionRow:
    level: float
    score: float
    visual_strength: float
    side: str
    sources: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StructureSnapshot:
    structure_version: str
    regime: StructureRegime
    trend_state: str
    momentum_state: MomentumState
    momentum_score: float
    primary_mm_target: StructureTarget | None
    secondary_mm_target: StructureTarget | None
    call_wall: float | None
    put_wall: float | None
    gamma_flip: float | None
    execution_state: ExecutionState
    attraction_profile: list[AttractionRow] = field(default_factory=list)
    structure_bias: float = 0.0
    family_weights: FamilyWeights | None = None
    structure_trends: dict[str, float | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "structure_version": self.structure_version,
            "regime": self.regime,
            "trend_state": self.trend_state,
            "momentum_state": self.momentum_state,
            "momentum_score": self.momentum_score,
            "primary_mm_target": self.primary_mm_target.to_dict()
            if self.primary_mm_target
            else None,
            "secondary_mm_target": self.secondary_mm_target.to_dict()
            if self.secondary_mm_target
            else None,
            "call_wall": self.call_wall,
            "put_wall": self.put_wall,
            "gamma_flip": self.gamma_flip,
            "execution_state": self.execution_state,
            "attraction_profile": [r.to_dict() for r in self.attraction_profile],
            "structure_bias": self.structure_bias,
            "family_weights": self.family_weights.to_dict() if self.family_weights else None,
            "mm_reference_family_weights": MM_REFERENCE_FAMILY_WEIGHTS,
            "structure_trends": self.structure_trends,
        }


def round_strike(level: float) -> float:
    return float(round(level / _STRIKE_GRID) * _STRIKE_GRID)


def build_structure_snapshot(
    *,
    terminal_symbol: str,
    classic: dict[str, Any] | None,
    orderflow: dict[str, Any] | None,
    spot: float | None = None,
    state_hubs: dict[str, dict[str, Any]] | None = None,
    iv_floor_strike: float | None = None,
) -> StructureSnapshot | None:
    """Build StructureSnapshot from vendor payloads (P0 classic+orderflow; P1 + state hubs)."""
    if classic is None and not state_hubs:
        return None
    classic = classic or {}
    spot_f = _f(spot if spot is not None else classic.get("spot"))
    if spot_f is None and state_hubs:
        for payload in state_hubs.values():
            spot_f = _f(payload.get("spot"))
            if spot_f is not None:
                break
    if spot_f is None:
        return None

    orderflow = orderflow or {}
    zero_gamma = _f(classic.get("zero_gamma"))
    sum_gex_vol = _f(classic.get("sum_gex_vol"))

    regime = _classify_regime(spot_f, zero_gamma, sum_gex_vol)
    structure_bias = _structure_bias(spot_f, zero_gamma, sum_gex_vol, orderflow)
    momentum_score, momentum_state = _momentum(terminal_symbol, orderflow)

    call_wall = _of_strike(orderflow.get("zero_major_call_gamma"))
    put_wall = _of_strike(orderflow.get("zero_major_put_gamma"))

    candidates = _build_candidates(
        classic,
        orderflow or {},
        spot_f,
        state_hubs=state_hubs,
        iv_floor_strike=iv_floor_strike,
    )
    weights = family_weights_from_env()
    scored = _score_candidates(
        candidates,
        spot=spot_f,
        structure_bias=structure_bias,
        regime=regime,
        family_weights=weights,
    )
    primary = scored[0] if scored else None
    secondary = scored[1] if len(scored) > 1 else None

    profile = _attraction_profile(scored, spot=spot_f)
    exec_state = _execution_state(
        spot=spot_f,
        primary=primary,
        momentum_score=momentum_score,
        structure_bias=structure_bias,
        regime=regime,
    )
    trend_state = _trend_state(structure_bias, momentum_score)
    version = "p1" if state_hubs else "p0"
    trends = trend_summary(terminal_symbol)

    return StructureSnapshot(
        structure_version=version,
        regime=regime,
        trend_state=trend_state,
        momentum_state=momentum_state,
        momentum_score=momentum_score,
        primary_mm_target=primary,
        secondary_mm_target=secondary,
        call_wall=call_wall,
        put_wall=put_wall,
        gamma_flip=zero_gamma,
        execution_state=exec_state,
        attraction_profile=profile,
        structure_bias=structure_bias,
        family_weights=weights,
        structure_trends=trends,
    )


def _classify_regime(
    spot: float,
    zero_gamma: float | None,
    sum_gex_vol: float | None,
) -> StructureRegime:
    if zero_gamma is None or sum_gex_vol is None:
        return "transition"
    if abs(spot - zero_gamma) <= _ZERO_GAMMA_BAND:
        return "unstable_near_zero_gamma"
    if spot > zero_gamma and sum_gex_vol >= 0:
        return "positive_gamma"
    if spot < zero_gamma or sum_gex_vol < 0:
        return "negative_gamma"
    return "transition"


def _structure_bias(
    spot: float,
    zero_gamma: float | None,
    sum_gex_vol: float | None,
    orderflow: dict[str, Any],
) -> float:
    gex_bias = 0.0
    if zero_gamma is not None and np.isfinite(zero_gamma) and zero_gamma != 0:
        gex_bias = float(np.clip((spot - zero_gamma) / max(abs(zero_gamma), 1.0), -1.0, 1.0))
    if sum_gex_vol is not None and np.isfinite(sum_gex_vol):
        gex_bias = float(np.clip(0.7 * gex_bias + 0.3 * np.sign(sum_gex_vol), -1.0, 1.0))

    flow_raw = _f(orderflow.get("gex_orderflow")) or 0.0
    flow_bias = float(np.clip(flow_raw / _FLOW_SCALE, -1.0, 1.0))
    tide = _f(orderflow.get("dex_orderflow"))
    tide_bias = float(np.clip((tide or 0.0) / _DEX_SCALE, -1.0, 1.0)) if tide is not None else 0.0

    return float(
        np.clip(0.55 * gex_bias + 0.25 * tide_bias + 0.20 * flow_bias, -1.0, 1.0)
    )


def _momentum(
    terminal_symbol: str,
    orderflow: dict[str, Any],
) -> tuple[float, MomentumState]:
    dex = _f(orderflow.get("dex_orderflow")) or 0.0
    gex_flow = _f(orderflow.get("gex_orderflow")) or 0.0
    net_dex = _f(orderflow.get("zero_net_total_dex")) or 0.0

    flow_bias = float(
        np.clip(
            0.34 * np.sign(dex)
            + 0.26 * np.sign(net_dex)
            + 0.22 * np.sign(gex_flow),
            -1.0,
            1.0,
        )
    )
    g5 = trend_pct(terminal_symbol, "sum_gex_vol", lookback_sec=5 * 60)
    g15 = trend_pct(terminal_symbol, "sum_gex_vol", lookback_sec=15 * 60)
    gex_delta = 0.0
    if g5 is not None or g15 is not None:
        parts = [p for p in (g5, g15) if p is not None]
        norm = float(np.clip(np.mean(parts) if parts else 0.0, -1.0, 1.0))
        gex_delta = norm

    score = float(np.clip(0.68 * flow_bias + 0.32 * gex_delta, -1.0, 1.0))
    if score >= 0.22:
        state: MomentumState = "up_momentum"
    elif score <= -0.22:
        state = "down_momentum"
    elif abs(score) >= 0.10:
        state = "mixed_momentum"
    else:
        state = "flat_momentum"
    return score, state


@dataclass
class _CandidateAcc:
    gamma: float = 0.0
    vex: float = 0.0
    iv: float = 0.0
    other: float = 0.0
    sources: list[str] = field(default_factory=list)


def _build_candidates(
    classic: dict[str, Any],
    orderflow: dict[str, Any],
    spot: float,
    *,
    state_hubs: dict[str, dict[str, Any]] | None = None,
    iv_floor_strike: float | None = None,
) -> dict[float, _CandidateAcc]:
    """Map strike → family strength accumulators."""
    acc: dict[float, _CandidateAcc] = {}

    def add(level: Any, family: str, weight: float, source: str) -> None:
        strike = _f(level)
        if strike is None or weight <= 0:
            return
        key = round_strike(strike)
        bucket = acc.setdefault(key, _CandidateAcc())
        current = getattr(bucket, family)
        setattr(bucket, family, current + weight)
        bucket.sources.append(source)

    for key, src in (
        ("zero_gamma", "classic.zero_gamma"),
        ("major_pos_vol", "classic.major_pos_vol"),
        ("major_pos_oi", "classic.major_pos_oi"),
        ("major_neg_vol", "classic.major_neg_vol"),
        ("major_neg_oi", "classic.major_neg_oi"),
    ):
        add(classic.get(key), "gamma", 1.0, src)

    for pair in classic.get("max_priors") or []:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        strike, weight = _f(pair[0]), _f(pair[1])
        if strike is not None and weight is not None and weight > 0:
            add(strike, "gamma", min(weight, 3.0), "classic.max_priors")

    for row in classic.get("strikes") or []:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        strike = _f(row[0])
        v1 = abs(_f(row[1]) or 0.0)
        if strike is not None and v1 > 0:
            add(strike, "gamma", min(v1 / max(spot, 1.0), 2.0), "classic.strikes")

    for key, src in (
        ("zero_major_call_gamma", "orderflow.zero_major_call_gamma"),
        ("zero_major_put_gamma", "orderflow.zero_major_put_gamma"),
        ("zero_major_long_gamma", "orderflow.zero_major_long_gamma"),
        ("zero_major_short_gamma", "orderflow.zero_major_short_gamma"),
    ):
        add(orderflow.get(key), "other", 0.42, src)

    _ingest_state_hubs(acc, state_hubs or {}, spot, add)
    if iv_floor_strike is not None and np.isfinite(iv_floor_strike):
        add(iv_floor_strike, "iv", 0.55, "local.iv_floor")

    return acc


# Hub → (family, relative hub weight). Vanna deliberately below gamma for Pin Play D1.
_STATE_HUB_FAMILY: dict[str, tuple[str, float]] = {
    "gamma_zero": ("gamma", 0.50),
    "vanna_zero": ("vex", 0.22),
    "charm_zero": ("iv", 0.18),
    "delta_zero": ("other", 0.12),
}


def _ingest_state_hubs(
    acc: dict[float, _CandidateAcc],
    state_hubs: dict[str, dict[str, Any]],
    spot: float,
    add: Any,
) -> None:
    scale = max(spot * 0.001, 1.0)
    for hub_key, payload in state_hubs.items():
        mapping = _STATE_HUB_FAMILY.get(hub_key)
        if mapping is None or not isinstance(payload, dict):
            continue
        family, hub_weight = mapping
        for row in payload.get("strikes") or []:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            strike = _f(row[0])
            v1 = abs(_f(row[1]) or 0.0)
            v2 = abs(_f(row[2]) or 0.0) if len(row) > 2 else 0.0
            mag = max(v1, v2)
            if strike is None or mag <= 0:
                continue
            strength = min(mag / scale, 2.0) * hub_weight
            add(strike, family, strength, f"state.{hub_key}")
        for level_key in ("zero_gamma", "major_pos_vol", "major_neg_vol", "major_pos_oi", "major_neg_oi"):
            level = payload.get(level_key)
            if level is not None:
                add(level, family, hub_weight * 0.75, f"state.{hub_key}.{level_key}")


def _score_candidates(
    candidates: dict[float, _CandidateAcc],
    *,
    spot: float,
    structure_bias: float,
    regime: StructureRegime,
    family_weights: FamilyWeights,
) -> list[StructureTarget]:
    if not candidates:
        return []

    w = family_weights.normalized()
    strikes = sorted(candidates.keys())
    lo, hi = min(strikes), max(strikes)
    range_pts = max(hi - lo, _STRIKE_GRID * 4)

    scored: list[StructureTarget] = []
    for strike, fam in candidates.items():
        gamma_s = fam.gamma
        vex_s = min(fam.vex, _VEX_STRENGTH_CAP)
        iv_s = min(fam.iv, _IV_STRENGTH_CAP)
        other_s = fam.other
        gamma_scale = max(w.gamma, 0.01)
        source_strength = (
            gamma_s
            + vex_s * (w.vex / gamma_scale)
            + iv_s * (w.iv / gamma_scale)
            + other_s
        )
        if source_strength <= 0:
            continue

        source_norm = float(np.clip(source_strength / 4.5, 0.0, 1.0))
        family_mix = float(
            w.gamma * min(1.0, gamma_s / 2.5)
            + w.vex * min(1.0, vex_s / 1.8)
            + w.iv * min(1.0, iv_s / 1.8)
        )
        abs_distance = abs(strike - spot)
        distance_shape = float(
            np.clip(
                1.0 - abs(abs_distance - 0.44 * range_pts) / max(0.80 * range_pts, 1.0),
                0.0,
                1.0,
            )
        )
        direction = 1.0 if strike >= spot else -1.0
        regime_bonus = 0.15 if regime in ("positive_gamma", "unstable_near_zero_gamma") else 0.0
        counter_penalty = 0.12 if direction * structure_bias < -0.15 and abs_distance > range_pts * 0.35 else 0.0

        confidence = float(
            np.clip(
                34.0
                + 30.0 * source_norm
                + 20.0 * distance_shape
                + 18.0 * family_mix
                + 8.0 * regime_bonus
                + 12.0 * direction * structure_bias
                - counter_penalty,
                0.0,
                96.0,
            )
        )
        sources = fam.sources
        scored.append(
            StructureTarget(
                level=strike,
                score=confidence,
                distance_pts=abs_distance,
                sources=sorted(set(sources)),
            )
        )

    scored.sort(key=lambda t: t.score, reverse=True)
    return scored


def _attraction_profile(
    scored: list[StructureTarget],
    *,
    spot: float,
) -> list[AttractionRow]:
    if not scored:
        return []
    max_score = max(t.score for t in scored) or 1.0
    out: list[AttractionRow] = []
    for target in scored[:40]:
        side = "pin" if abs(target.level - spot) <= _STRIKE_GRID else ("up" if target.level > spot else "down")
        visual = float(np.clip(100.0 * target.score / max(max_score, 1.0), 0.0, 100.0))
        out.append(
            AttractionRow(
                level=target.level,
                score=target.score,
                visual_strength=visual,
                side=side,
                sources=target.sources,
            )
        )
    return out


def _execution_state(
    *,
    spot: float,
    primary: StructureTarget | None,
    momentum_score: float,
    structure_bias: float,
    regime: StructureRegime,
) -> ExecutionState:
    if primary is not None and abs(spot - primary.level) <= _STRIKE_GRID:
        return "at_mm_target_pin_or_take_profit"
    if abs(momentum_score) >= 0.22 and np.sign(momentum_score) != np.sign(structure_bias):
        return "dynamic_conflict_pin_wait"
    if primary is not None and regime != "transition":
        return "macro_target_watch"
    return "transition"


def _trend_state(structure_bias: float, momentum_score: float) -> str:
    combined = 0.6 * structure_bias + 0.4 * momentum_score
    if combined >= 0.15:
        return "bullish"
    if combined <= -0.15:
        return "bearish"
    return "neutral"


def _of_strike(raw: Any) -> float | None:
    val = _f(raw)
    if val is None or val <= 0:
        return None
    return round_strike(val)


def _f(val: Any) -> float | None:
    try:
        out = float(val)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None
