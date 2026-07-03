"""Tests for pin center fusion."""

from __future__ import annotations

from quant_lab.terminal.mm_structure import StructureSnapshot, StructureTarget
from quant_lab.terminal.pin_center import PhysicalSnapshot, fuse_pin_center


def _physical(*, king: float = 7135.0, pin: float = 75.0) -> PhysicalSnapshot:
    return PhysicalSnapshot(
        spot=7130.0,
        king_bs=king,
        flip_bs=7125.0,
        call_wall_bs=7150.0,
        put_wall_bs=7100.0,
        max_pain=7130.0,
        pin_score=pin,
        regime_local="long_gamma",
        pct_gex_dte1=45.0,
        expected_move_1sd=35.0,
        magnet_strike=king,
    )


def _structure(primary_level: float) -> StructureSnapshot:
    primary = StructureTarget(
        level=primary_level,
        score=82.0,
        distance_pts=5.0,
        sources=["classic.major_pos_vol"],
    )
    return StructureSnapshot(
        structure_version="p0",
        regime="positive_gamma",
        trend_state="neutral",
        momentum_state="flat_momentum",
        momentum_score=0.05,
        primary_mm_target=primary,
        secondary_mm_target=None,
        call_wall=7140.0,
        put_wall=7100.0,
        gamma_flip=7125.0,
        execution_state="macro_target_watch",
    )


def test_fuse_high_confidence_when_king_primary_priors_agree() -> None:
    decision = fuse_pin_center(
        _physical(king=7135.0),
        _structure(7135.0),
        max_priors=[(7135.0, 2.0)],
    )
    assert decision.center_source == "fused"
    assert decision.center_confidence == "high"
    assert decision.pin_center == 7135.0
    assert decision.entry_blocked is False


def test_fuse_uses_primary_when_diverge_and_pin_strong() -> None:
    decision = fuse_pin_center(
        _physical(king=7100.0, pin=78.0),
        _structure(7140.0),
        max_priors=[(7140.0, 1.5)],
    )
    assert decision.center_source == "primary_mm"
    assert decision.pin_center == 7140.0
    assert decision.size_overlay == 1.0


def test_fuse_blocks_on_structure_momentum_conflict() -> None:
    structure = _structure(7140.0)
    structure.execution_state = "dynamic_conflict_pin_wait"
    decision = fuse_pin_center(_physical(), structure)
    assert decision.entry_blocked is True
    assert decision.entry_blocked_reason == "structure_momentum_conflict"
