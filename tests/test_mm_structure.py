"""Tests for MM structure snapshot (P0)."""

from __future__ import annotations

from quant_lab.terminal.mm_structure import (
    FamilyWeights,
    MM_REFERENCE_FAMILY_WEIGHTS,
    PIN_PLAY_FAMILY_WEIGHTS,
    _CandidateAcc,
    _score_candidates,
    build_structure_snapshot,
)


def _classic_fixture() -> dict:
    return {
        "spot": 7130.0,
        "zero_gamma": 7125.0,
        "sum_gex_vol": 1_200_000.0,
        "major_pos_vol": 7135.0,
        "major_neg_vol": 7100.0,
        "max_priors": [[7135.0, 2.5], [7140.0, 1.0]],
    }


def _orderflow_fixture() -> dict:
    return {
        "spot": 7130.0,
        "zero_major_call_gamma": 7140.0,
        "zero_major_put_gamma": 7100.0,
        "gex_orderflow": 120.0,
        "dex_orderflow": 80.0,
        "zero_net_total_dex": 50.0,
    }


def test_build_structure_snapshot_primary_near_spot() -> None:
    snap = build_structure_snapshot(
        terminal_symbol="^SPX",
        classic=_classic_fixture(),
        orderflow=_orderflow_fixture(),
        spot=7130.0,
    )
    assert snap is not None
    assert snap.structure_version == "p0"
    assert snap.primary_mm_target is not None
    assert snap.primary_mm_target.level in (7130.0, 7135.0, 7140.0)
    assert snap.regime in ("positive_gamma", "unstable_near_zero_gamma")
    assert len(snap.attraction_profile) >= 1


def test_build_structure_snapshot_returns_none_without_classic() -> None:
    assert build_structure_snapshot(
        terminal_symbol="^SPX",
        classic=None,
        orderflow=_orderflow_fixture(),
    ) is None


def test_pin_play_weights_favor_gamma_over_equal_vanna() -> None:
    """Vanna family_mix is capped below MM reference so gamma pins win D1 ties."""
    spot = 7130.0
    candidates = {
        7135.0: _CandidateAcc(gamma=1.0, vex=0.0, iv=0.0, sources=["classic.major_pos_vol"]),
        7140.0: _CandidateAcc(gamma=0.0, vex=2.4, iv=0.0, sources=["state.vanna"]),
    }
    pin_w = FamilyWeights(
        PIN_PLAY_FAMILY_WEIGHTS["gamma"],
        PIN_PLAY_FAMILY_WEIGHTS["vex"],
        PIN_PLAY_FAMILY_WEIGHTS["iv"],
        "pin_play_p0",
    )
    mm_w = FamilyWeights(
        MM_REFERENCE_FAMILY_WEIGHTS["gamma"],
        MM_REFERENCE_FAMILY_WEIGHTS["vex"],
        MM_REFERENCE_FAMILY_WEIGHTS["iv"],
        "mm_reference",
    )
    pin_scored = _score_candidates(
        candidates,
        spot=spot,
        structure_bias=0.0,
        regime="positive_gamma",
        family_weights=pin_w,
    )
    mm_scored = _score_candidates(
        candidates,
        spot=spot,
        structure_bias=0.0,
        regime="positive_gamma",
        family_weights=mm_w,
    )
    assert pin_scored[0].level == 7135.0
    assert mm_scored[0].level == 7140.0
