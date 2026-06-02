"""Live ``time=live`` pin data-quality grading for the Index terminal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from quant_lab.factors.gex import TimeToExpiryDiagnostics
from quant_lab.factors.regime import PinReliability

LivePinGrade = Literal["ok", "degraded", "poor"]

_RELIABILITY_RANK: dict[PinReliability, int] = {
    "high": 4,
    "moderate": 3,
    "caution": 2,
    "low": 1,
    "unknown": 0,
}

_RANK_TO_TIER: dict[int, PinReliability] = {
    4: "high",
    3: "moderate",
    2: "caution",
    1: "low",
    0: "unknown",
}


@dataclass(frozen=True)
class LivePinQuality:
    """Whether today's live poll is trustworthy for pin/GEX reads."""

    grade: LivePinGrade
    live_follow: bool
    reasons: tuple[str, ...]
    chain_from_cache: bool
    chain_stale_served: bool
    chain_age_seconds: float | None
    hours_to_close: float | None
    n_strikes: int


def assess_live_pin_quality(
    *,
    is_live_poll: bool,
    live_follow: bool,
    data_source: str,
    cohort_fallback: bool,
    t_diag: TimeToExpiryDiagnostics,
    n_strikes: int,
    flip_confidence: str | None,
    chain_poll: dict[str, Any] | None,
    hours_to_close: float | None,
    main_chain_source: str | None,
) -> LivePinQuality | None:
    """Grade live pin context; None when not a live ThetaData session."""
    if not is_live_poll:
        return None
    if main_chain_source != "live" and data_source != "thetadata_live":
        return None

    reasons: list[str] = []
    grade: LivePinGrade = "ok"

    from_cache = bool(chain_poll and chain_poll.get("from_cache"))
    stale_served = bool(chain_poll and chain_poll.get("stale_served"))
    age = chain_poll.get("chain_age_seconds") if chain_poll else None
    age_f = float(age) if age is not None else None

    if cohort_fallback:
        reasons.append("0DTE cohort empty — using full chain for GEX/pin.")
        grade = "degraded"
    if t_diag.fallback_used or t_diag.mode == "fallback_1h":
        reasons.append("Time-to-expiry fallback — intraday gamma may be mis-scaled.")
        grade = "poor"
    elif t_diag.mode not in ("exact_intraday", "hours_to_close"):
        reasons.append(f"Time-to-expiry mode is {t_diag.mode}, not session clock.")
        grade = "degraded"
    if n_strikes < 20:
        reasons.append(f"Sparse chain ({n_strikes} strikes) — pin ladder thin.")
        grade = "degraded" if grade == "ok" else grade
    if flip_confidence in ("low", "none"):
        reasons.append("Gamma flip confidence low — treat flip as a zone.")
        if grade == "ok":
            grade = "degraded"
    if stale_served:
        reasons.append("Serving stale ThetaData cache after fetch error.")
        grade = "poor"
    elif from_cache and age_f is not None and age_f > 90.0:
        reasons.append(f"Chain snapshot is {age_f:.0f}s old — levels may lag.")
        grade = "degraded" if grade == "ok" else grade

    if not reasons:
        reasons.append("Live 0DTE chain with session-clock T.")

    return LivePinQuality(
        grade=grade,
        live_follow=live_follow,
        reasons=tuple(reasons),
        chain_from_cache=from_cache,
        chain_stale_served=stale_served,
        chain_age_seconds=age_f,
        hours_to_close=hours_to_close,
        n_strikes=n_strikes,
    )


def cap_pin_reliability(
    tier: PinReliability,
    detail: str,
    quality: LivePinQuality | None,
) -> tuple[PinReliability, str]:
    """Downgrade pin reliability tier when live data quality is weak."""
    if quality is None:
        return tier, detail
    cap_rank = _RELIABILITY_RANK[tier]
    if quality.grade == "poor":
        cap_rank = min(cap_rank, _RELIABILITY_RANK["low"])
        detail = f"{detail} · Live data quality poor"
    elif quality.grade == "degraded":
        cap_rank = min(cap_rank, _RELIABILITY_RANK["moderate"])
        detail = f"{detail} · Live data degraded"
    capped = _RANK_TO_TIER[cap_rank]
    if quality.reasons and quality.grade != "ok":
        top = quality.reasons[0]
        if top not in detail:
            detail = f"{detail} — {top}"
    return capped, detail


def live_pin_quality_to_dict(quality: LivePinQuality | None) -> dict[str, Any] | None:
    if quality is None:
        return None
    return {
        "grade": quality.grade,
        "live_follow": quality.live_follow,
        "reasons": list(quality.reasons),
        "chain_from_cache": quality.chain_from_cache,
        "chain_stale_served": quality.chain_stale_served,
        "chain_age_seconds": quality.chain_age_seconds,
        "hours_to_close": quality.hours_to_close,
        "n_strikes": quality.n_strikes,
    }
