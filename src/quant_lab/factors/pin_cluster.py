"""Pinning zone detection from adjacent magnet strikes.

When two top magnet levels are close in price and similar in |GEX|×OI weight,
they form a **pinning cluster** (gamma concentration band), not competing point
targets.  Pure functions only — no I/O (``factors/`` boundary).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

ClusterStrength = Literal["high", "moderate", "low", "none"]
SpotZoneState = Literal[
    "inside_zone",
    "testing_upside_exit",
    "testing_downside_exit",
    "above_break",
    "below_break",
    "unknown",
]

# Defaults — revisit via ``scripts/calibrate_pin_cluster.py`` (Phase P2).
CLUSTER_MAX_DIST_PCT = 0.003
CLUSTER_MIN_STRENGTH_RATIO = 0.70
CLUSTER_HIGH_STRENGTH_RATIO = 0.85
BUFFER_WIDTH_FRAC = 0.25
BUFFER_TICK_FLOOR_SPX = 5.0
BUFFER_TICK_FLOOR_SPY = 0.5


@dataclass(frozen=True)
class PinZoneBreak:
    """Buffer-adjusted break levels outside the pinning cluster."""

    up_break_level: float
    down_break_level: float
    buffer_pts: float


@dataclass(frozen=True)
class PinClusterResult:
    """Merged pinning zone from two adjacent magnet strikes."""

    is_cluster: bool
    lower: float
    upper: float
    center: float
    width: float
    primary_strike: float
    secondary_strike: float | None
    strength_ratio: float
    cluster_strength: ClusterStrength
    merge_reason: str
    zone_break: PinZoneBreak | None
    spot_zone_state: SpotZoneState


def _tick_floor(symbol: str | None, spot: float) -> float:
    if symbol is not None:
        sym = symbol.replace("^", "").upper()
        if sym in ("SPX", "SPXW"):
            return BUFFER_TICK_FLOOR_SPX
        if sym in ("SPY", "QQQ", "IWM"):
            return BUFFER_TICK_FLOOR_SPY
    return BUFFER_TICK_FLOOR_SPX if spot >= 500.0 else BUFFER_TICK_FLOOR_SPY


def zone_buffer_pts(*, zone_width: float, symbol: str | None, spot: float) -> float:
    """``max(tick_floor, BUFFER_WIDTH_FRAC × zone_width)``."""
    floor = _tick_floor(symbol, spot)
    return float(max(floor, BUFFER_WIDTH_FRAC * zone_width))


def compute_zone_break(
    zone_low: float,
    zone_high: float,
    *,
    symbol: str | None,
    spot: float,
) -> PinZoneBreak:
    """Break levels above/below the cluster with instrument-aware buffer."""
    width = zone_high - zone_low
    buffer = zone_buffer_pts(zone_width=width, symbol=symbol, spot=spot)
    return PinZoneBreak(
        up_break_level=zone_high + buffer,
        down_break_level=zone_low - buffer,
        buffer_pts=buffer,
    )


def spot_zone_state(
    spot: float,
    *,
    zone_low: float,
    zone_high: float,
    zone_break: PinZoneBreak,
) -> SpotZoneState:
    """Point-in-time zone state (no bar confirmation — live adds that in Phase 4)."""
    if not np.isfinite(spot):
        return "unknown"
    if zone_low <= spot <= zone_high:
        return "inside_zone"
    if spot > zone_break.up_break_level:
        return "above_break"
    if spot < zone_break.down_break_level:
        return "below_break"
    if spot > zone_high:
        return "testing_upside_exit"
    return "testing_downside_exit"


def _cluster_strength_label(ratio: float) -> ClusterStrength:
    if ratio >= CLUSTER_HIGH_STRENGTH_RATIO:
        return "high"
    if ratio >= CLUSTER_MIN_STRENGTH_RATIO:
        return "moderate"
    return "low"


def _ranked_magnet_rows(
    rankings: list[dict[str, float | list[str] | None]],
) -> list[tuple[float, float]]:
    """Return (strike, weight_pct) for rows with positive magnet weight."""
    rows: list[tuple[float, float]] = []
    for row in rankings:
        strike = row.get("strike")
        weight = row.get("weight_pct")
        if strike is None or weight is None:
            continue
        strike_f = float(strike)
        weight_f = float(weight)
        if not np.isfinite(strike_f) or not np.isfinite(weight_f) or weight_f <= 0:
            continue
        rows.append((strike_f, weight_f))
    return rows


def detect_pin_cluster(
    rankings: list[dict[str, float | list[str] | None]],
    spot: float,
    *,
    symbol: str | None = None,
    regime: str = "undetermined",
    pin_reliability: str = "unknown",
    macro_blocked: bool = False,
    max_dist_pct: float = CLUSTER_MAX_DIST_PCT,
    min_strength_ratio: float = CLUSTER_MIN_STRENGTH_RATIO,
) -> PinClusterResult:
    """Detect whether top-2 magnets merge into a pinning zone.

    Returns ``is_cluster=False`` when merge gates fail; ``spot_zone_state`` is
    still ``unknown`` in that case.
    """
    empty = PinClusterResult(
        is_cluster=False,
        lower=float("nan"),
        upper=float("nan"),
        center=float("nan"),
        width=float("nan"),
        primary_strike=float("nan"),
        secondary_strike=None,
        strength_ratio=float("nan"),
        cluster_strength="none",
        merge_reason="no_cluster",
        zone_break=None,
        spot_zone_state="unknown",
    )

    if not rankings or not np.isfinite(spot) or spot <= 0:
        return empty

    weighted = _ranked_magnet_rows(rankings)
    if len(weighted) < 2:
        return replace(empty, merge_reason="insufficient_magnets")

    primary_strike, primary_w = weighted[0]
    secondary_strike, secondary_w = weighted[1]
    if primary_w <= 0:
        return empty

    strength_ratio = secondary_w / primary_w
    dist_pct = abs(primary_strike - secondary_strike) / spot

    if macro_blocked:
        return replace(empty, merge_reason="macro_event_active")

    if regime == "short_gamma":
        return replace(empty, merge_reason="short_gamma_regime")

    if pin_reliability in ("low", "unknown") and regime != "long_gamma":
        return replace(empty, merge_reason="low_pin_reliability")

    if dist_pct >= max_dist_pct:
        return replace(empty, merge_reason="strikes_too_far_apart")

    if strength_ratio < min_strength_ratio:
        return replace(empty, merge_reason="secondary_too_weak")

    lower = min(primary_strike, secondary_strike)
    upper = max(primary_strike, secondary_strike)
    width = upper - lower
    center = (lower + upper) / 2.0
    zone_break = compute_zone_break(lower, upper, symbol=symbol, spot=spot)
    state = spot_zone_state(
        spot,
        zone_low=lower,
        zone_high=upper,
        zone_break=zone_break,
    )

    return PinClusterResult(
        is_cluster=True,
        lower=lower,
        upper=upper,
        center=center,
        width=width,
        primary_strike=primary_strike,
        secondary_strike=secondary_strike,
        strength_ratio=float(strength_ratio),
        cluster_strength=_cluster_strength_label(strength_ratio),
        merge_reason="adjacent_gex_peaks",
        zone_break=zone_break,
        spot_zone_state=state,
    )


def pin_cluster_interpretation(result: PinClusterResult) -> str:
    """One-line model-implied readout for UI (non-deterministic wording)."""
    if not result.is_cluster or result.zone_break is None:
        return ""
    state = result.spot_zone_state
    lo = result.lower
    hi = result.upper
    if state == "inside_zone":
        return (
            f"Price is inside the model-implied {lo:.0f}–{hi:.0f} pinning zone. "
            "Realized volatility may stay dampened unless flow breaks the cluster."
        )
    if state == "testing_upside_exit":
        return (
            f"Price is testing above {hi:.0f}. Treat as unconfirmed until "
            f"5m closes hold above {result.zone_break.up_break_level:.0f}."
        )
    if state == "testing_downside_exit":
        return (
            f"Price is testing below {lo:.0f}. Treat as unconfirmed until "
            f"5m closes hold below {result.zone_break.down_break_level:.0f}."
        )
    if state == "above_break":
        return (
            f"Price is above the upside break ({result.zone_break.up_break_level:.0f}). "
            "Prior pin zone may be weakening — watch the next upside gamma level."
        )
    if state == "below_break":
        return (
            f"Price is below the downside break ({result.zone_break.down_break_level:.0f}). "
            "Prior pin zone may be weakening — watch the next downside gamma level."
        )
    return (
        f"Model identifies a {lo:.0f}–{hi:.0f} pinning cluster from adjacent gamma peaks. "
        "Interpret as a zone, not a precise target."
    )


def pin_cluster_to_dict(result: PinClusterResult) -> dict[str, float | str | bool | None]:
    """JSON-safe cluster payload for terminal ``pin_targets``."""
    zb = result.zone_break
    return {
        "is_cluster": result.is_cluster,
        "lower": float(result.lower) if result.is_cluster else None,
        "upper": float(result.upper) if result.is_cluster else None,
        "center": float(result.center) if result.is_cluster else None,
        "width": float(result.width) if result.is_cluster else None,
        "primary_strike": float(result.primary_strike) if result.is_cluster else None,
        "secondary_strike": (
            float(result.secondary_strike)
            if result.is_cluster and result.secondary_strike is not None
            else None
        ),
        "strength_ratio": float(result.strength_ratio) if result.is_cluster else None,
        "cluster_strength": result.cluster_strength if result.is_cluster else "none",
        "merge_reason": result.merge_reason,
        "spot_zone_state": result.spot_zone_state if result.is_cluster else None,
        "interpretation": pin_cluster_interpretation(result) if result.is_cluster else None,
        "up_break_level": float(zb.up_break_level) if zb is not None else None,
        "down_break_level": float(zb.down_break_level) if zb is not None else None,
        "buffer_pts": float(zb.buffer_pts) if zb is not None else None,
    }
