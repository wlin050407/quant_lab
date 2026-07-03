"""Fuse local physical snapshot with MM structure into Pin Play fly center."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np

from quant_lab.config import env_var
from quant_lab.terminal.mm_structure import StructureSnapshot, round_strike

CenterConfidence = Literal["high", "medium", "low"]
CenterSource = Literal[
    "fused",
    "king_bs",
    "primary_mm",
    "max_priors",
    "max_pain",
    "close_pin",
    "spot",
]


@dataclass(frozen=True)
class PhysicalSnapshot:
    spot: float
    king_bs: float | None
    flip_bs: float | None
    call_wall_bs: float | None
    put_wall_bs: float | None
    max_pain: float | None
    pin_score: float | None
    regime_local: str
    pct_gex_dte1: float | None
    expected_move_1sd: float | None
    magnet_strike: float | None


@dataclass
class PinCenterDecision:
    pin_center: float
    center_source: CenterSource
    center_confidence: CenterConfidence
    candidates: dict[str, float]
    size_overlay: float
    entry_blocked: bool
    entry_blocked_reason: str | None
    narrative: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _env_float(name: str, default: float) -> float:
    raw = env_var(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _prior_peak(max_priors: list[tuple[float, float]] | None) -> float | None:
    if not max_priors:
        return None
    best: tuple[float, float] | None = None
    for strike, weight in max_priors:
        if not np.isfinite(strike):
            continue
        if best is None or weight > best[1]:
            best = (float(strike), float(weight))
    return round_strike(best[0]) if best is not None else None


def fuse_pin_center(
    physical: PhysicalSnapshot,
    structure: StructureSnapshot | None,
    *,
    max_priors: list[tuple[float, float]] | None = None,
    minutes_to_close: float | None = None,
    resonance_tier: str | None = None,
) -> PinCenterDecision:
    """Decide iron-fly center K and overlays for Playbook."""
    strike_tol = _env_float("PIN_CENTER_STRIKE_TOL", 5.0)
    diverge_tol = _env_float("PIN_CENTER_DIVERGE_TOL", 10.0)
    conflict_size = _env_float("PIN_CENTER_CONFLICT_SIZE", 0.5)
    close_minutes = _env_float("PIN_CENTER_CLOSE_PIN_MINUTES", 90.0)

    c_king = round_strike(physical.king_bs) if physical.king_bs is not None else None
    c_pri = (
        round_strike(structure.primary_mm_target.level)
        if structure is not None and structure.primary_mm_target is not None
        else None
    )
    c_prior = _prior_peak(max_priors)
    c_pain = round_strike(physical.max_pain) if physical.max_pain is not None else None
    c_close = (
        round_strike(physical.spot)
        if minutes_to_close is not None and minutes_to_close <= close_minutes
        else None
    )

    candidates = {
        k: v
        for k, v in (
            ("king_bs", c_king),
            ("primary_mm", c_pri),
            ("max_priors", c_prior),
            ("max_pain", c_pain),
            ("close_pin", c_close),
        )
        if v is not None and np.isfinite(v)
    }

    pin_center: float | None = None
    source: CenterSource = "king_bs"
    confidence: CenterConfidence = "medium"
    size_overlay = 1.0
    narrative_parts: list[str] = []

    def _aligned(a: float | None, b: float | None) -> bool:
        return a is not None and b is not None and abs(a - b) <= strike_tol

    if (
        c_king is not None
        and c_pri is not None
        and c_prior is not None
        and _aligned(c_king, c_pri)
        and _aligned(c_king, c_prior)
    ):
        pin_center = round_strike((c_king + c_pri) / 2.0)
        source = "fused"
        confidence = "high"
        narrative_parts.append("King, GEXBot primary, and max_priors agree.")

    if pin_center is None and c_king is not None and c_pri is not None:
        if abs(c_king - c_pri) > diverge_tol:
            pin_ok = physical.pin_score is not None and physical.pin_score >= 70.0
            momentum_ok = structure is None or structure.execution_state not in (
                "dynamic_conflict_pin_wait",
            )
            if pin_ok and momentum_ok:
                pin_center = c_pri
                source = "primary_mm"
                confidence = "medium"
                narrative_parts.append(
                    f"King ({c_king:.0f}) vs primary ({c_pri:.0f}) diverge — using GEXBot primary."
                )
            else:
                pin_center = c_king
                source = "king_bs"
                confidence = "low"
                size_overlay = conflict_size
                narrative_parts.append(
                    f"King vs primary diverge by {abs(c_king - c_pri):.0f}pt — conservative King center."
                )
        elif _aligned(c_king, c_pri):
            pin_center = c_king
            source = "king_bs"
            confidence = "high"
            narrative_parts.append("King aligns with GEXBot primary.")

    if pin_center is None:
        for key, val in (
            ("king_bs", c_king),
            ("primary_mm", c_pri),
            ("max_priors", c_prior),
            ("max_pain", c_pain),
        ):
            if val is not None:
                pin_center = val
                source = key  # type: ignore[assignment]
                confidence = "medium" if key != "max_pain" else "low"
                break

    if pin_center is None and np.isfinite(physical.spot):
        pin_center = round_strike(physical.spot)
        source = "spot"
        confidence = "low"
        narrative_parts.append("Fallback to spot-rounded center.")

    if pin_center is None:
        return PinCenterDecision(
            pin_center=float("nan"),
            center_source="spot",
            center_confidence="low",
            candidates=candidates,
            size_overlay=0.0,
            entry_blocked=True,
            entry_blocked_reason="no_pin_center",
            narrative="No valid pin center candidate.",
        )

    if (
        c_close is not None
        and minutes_to_close is not None
        and minutes_to_close <= close_minutes
        and physical.pin_score is not None
        and physical.pin_score >= 60.0
        and c_king is not None
        and abs(c_close - c_king) > strike_tol
        and abs(c_close - pin_center) <= strike_tol
    ):
        pin_center = c_close
        source = "close_pin"
        narrative_parts.append("Close-window near-spot pin emphasis.")

    entry_blocked = False
    block_reason: str | None = None
    if structure is not None and structure.execution_state == "dynamic_conflict_pin_wait":
        entry_blocked = True
        block_reason = "structure_momentum_conflict"
        narrative_parts.append("Structure and momentum conflict — wait.")
    if confidence == "low" and (physical.pin_score is None or physical.pin_score < 75.0):
        entry_blocked = True
        block_reason = block_reason or "low_center_confidence"
    if resonance_tier == "low" and (physical.pin_score is None or physical.pin_score < 75.0):
        size_overlay = min(size_overlay, conflict_size)
        narrative_parts.append("Low vendor resonance — reduced size.")

    if not narrative_parts:
        narrative_parts.append(f"Pin center {pin_center:.0f} from {source}.")

    return PinCenterDecision(
        pin_center=float(pin_center),
        center_source=source,
        center_confidence=confidence,
        candidates=candidates,
        size_overlay=float(size_overlay),
        entry_blocked=entry_blocked,
        entry_blocked_reason=block_reason,
        narrative=" ".join(narrative_parts),
    )
