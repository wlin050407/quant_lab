"""Live pin data-quality grading."""

from __future__ import annotations

from quant_lab.factors.gex import TimeToExpiryDiagnostics
from quant_lab.terminal.live_pin_quality import assess_live_pin_quality, cap_pin_reliability


def test_assess_live_ok_when_intraday_t() -> None:
    t = TimeToExpiryDiagnostics(
        mode="hours_to_close",
        fallback_used=False,
        t_years_median=3.0 / (365 * 6.5),
        warning=None,
    )
    q = assess_live_pin_quality(
        is_live_poll=True,
        live_follow=True,
        data_source="thetadata_live",
        cohort_fallback=False,
        t_diag=t,
        n_strikes=120,
        flip_confidence="high",
        chain_poll={"from_cache": False, "stale_served": False, "chain_age_seconds": 12.0},
        hours_to_close=3.0,
        main_chain_source="live",
    )
    assert q is not None
    assert q.grade == "ok"


def test_assess_live_poor_on_t_fallback() -> None:
    t = TimeToExpiryDiagnostics(
        mode="fallback_1h",
        fallback_used=True,
        t_years_median=1.0 / (365 * 6.5),
        warning="fallback",
    )
    q = assess_live_pin_quality(
        is_live_poll=True,
        live_follow=True,
        data_source="thetadata_live",
        cohort_fallback=False,
        t_diag=t,
        n_strikes=80,
        flip_confidence="medium",
        chain_poll=None,
        hours_to_close=2.0,
        main_chain_source="live",
    )
    assert q is not None
    assert q.grade == "poor"


def test_cap_pin_reliability_downgrades_tier() -> None:
    from quant_lab.terminal.live_pin_quality import LivePinQuality

    q = LivePinQuality(
        grade="poor",
        live_follow=True,
        reasons=("T fallback",),
        chain_from_cache=False,
        chain_stale_served=False,
        chain_age_seconds=None,
        hours_to_close=1.0,
        n_strikes=50,
    )
    tier, detail = cap_pin_reliability("high", "High pin", q)
    assert tier in ("low", "caution", "moderate")
    assert "poor" in detail.lower() or "fallback" in detail.lower()
