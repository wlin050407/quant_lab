"""Tests for vendor/local resonance scoring."""

from __future__ import annotations

from quant_lab.factors.regime import should_trade_with_resonance
from quant_lab.terminal.resonance import (
    ResonanceLocal,
    ResonanceVendor,
    compute_resonance,
)


def test_resonance_high_when_flip_magnet_pin_align() -> None:
    local = ResonanceLocal(
        spot=7130.0,
        flip=7125.0,
        king=7135.0,
        max_pain=7130.0,
        pin_score=72.0,
        regime="long_gamma",
    )
    vendor = ResonanceVendor(
        zero_gamma=7126.0,
        major_pos_oi=7135.0,
        major_neg_oi=7100.0,
        max_priors=[(7135.0, 1_000_000.0), (7140.0, 100_000.0)],
        gex_orderflow=50.0,
    )
    report = compute_resonance(local, vendor, flip_tol_pts=15.0, magnet_tol_strikes=1.0)
    assert report.tier == "high"
    assert report.score >= 0.75
    assert report.axes["flip_align"] >= 0.9
    assert report.axes["wall_cage"] == 1.0


def test_resonance_low_when_flip_diverges() -> None:
    local = ResonanceLocal(
        spot=7130.0,
        flip=7180.0,
        king=7135.0,
        max_pain=7130.0,
        pin_score=55.0,
        regime="short_gamma",
    )
    vendor = ResonanceVendor(
        zero_gamma=7100.0,
        major_pos_oi=7200.0,
        major_neg_oi=7050.0,
        max_priors=[(7200.0, 500_000.0)],
        gex_orderflow=100.0,
    )
    report = compute_resonance(local, vendor, flip_tol_pts=15.0)
    assert report.tier == "low"
    assert any(d.field == "flip" for d in report.divergences)


def test_resonance_unavailable_without_vendor() -> None:
    local = ResonanceLocal(
        spot=7000.0,
        flip=6990.0,
        king=7010.0,
        max_pain=7005.0,
        pin_score=40.0,
        regime="undetermined",
    )
    report = compute_resonance(local, None)
    assert report.tier == "unavailable"


def test_should_trade_with_resonance_blocks_low_tier_moderate_pin() -> None:
    ok, reason = should_trade_with_resonance(
        base_ok=True,
        base_reason="ok",
        pin_score=60.0,
        resonance_tier="low",
    )
    assert ok is False
    assert reason == "low_resonance"


def test_should_trade_with_resonance_allows_high_pin_despite_low_tier() -> None:
    ok, reason = should_trade_with_resonance(
        base_ok=True,
        base_reason="ok",
        pin_score=80.0,
        resonance_tier="low",
    )
    assert ok is True
    assert reason == "ok"
