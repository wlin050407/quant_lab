"""Assemble model-implied positioning metadata for terminal API payloads."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from quant_lab.factors.gex import (
    DEFAULT_DEALER_SIGN,
    GammaFlipResult,
    TimeToExpiryDiagnostics,
    compute_gamma_flip,
    diagnose_cohort_time_to_expiry,
)
from quant_lab.factors.rates import GexInputs

DEALER_SIGN_ASSUMPTION = "SpotGamma-style: dealer long calls (+1), short puts (-1)"
INTERPRETATION_WARNING = (
    "Dealer positioning is inferred from open interest and a sign convention, "
    "not directly observed."
)
VEX_INTERPRETATION_WARNING = (
    "VEX assumes a parallel IV shock and the default dealer sign convention. "
    "Real dealer hedging may differ."
)


def build_model_metadata(
    *,
    gex_inputs: GexInputs,
    chain: pd.DataFrame | None,
    spot: float,
    dte_max: int = 1,
    hours_to_close: float | None = None,
    data_source: str,
    oi_mode: str | None = None,
    flip_result: GammaFlipResult | None = None,
    extra_warnings: list[str] | None = None,
    live_pin_quality: dict[str, Any] | None = None,
    live_chain_poll: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """JSON-safe model + data-quality block for ``snapshot.meta``."""
    t_diag = diagnose_cohort_time_to_expiry(
        chain if chain is not None else pd.DataFrame(),
        dte_max=dte_max,
        hours_to_close=hours_to_close,
    )
    warnings: list[str] = []
    if t_diag.warning:
        warnings.append(t_diag.warning)
    if extra_warnings:
        warnings.extend(extra_warnings)
    if live_pin_quality and live_pin_quality.get("grade") in ("degraded", "poor"):
        for reason in live_pin_quality.get("reasons") or []:
            if reason not in warnings:
                warnings.append(str(reason))

    flip_detail: dict[str, Any] | None = None
    if flip_result is not None:
        flip_detail = {
            "primary_flip": _finite_or_none(flip_result.primary_flip),
            "primary_rule": flip_result.primary_rule,
            "all_flips": [_finite_or_none(f) for f in flip_result.all_flips],
            "search_radius_pct": flip_result.search_radius_pct,
            "grid_points": flip_result.n_search_points,
            "confidence": flip_result.confidence,
        }

    return {
        "dealer_sign_assumption": DEALER_SIGN_ASSUMPTION,
        "dealer_sign_observed": False,
        "dealer_sign": dict(DEFAULT_DEALER_SIGN),
        "interpretation_warning": INTERPRETATION_WARNING,
        "vex_interpretation_warning": VEX_INTERPRETATION_WARNING,
        "pricing_inputs": {
            "model": gex_inputs.model,
            "r": gex_inputs.r,
            "q": gex_inputs.q,
            "rate_source": gex_inputs.r_source,
            "dividend_source": gex_inputs.q_source,
        },
        "time_to_expiry": {
            "mode": t_diag.mode,
            "fallback_used": t_diag.fallback_used,
            "t_years_median": _finite_or_none(t_diag.t_years_median),
            "warning": t_diag.warning,
        },
        "gamma_flip": flip_detail,
        "oi_source": data_source,
        "oi_mode": oi_mode,
        "data_quality_warnings": warnings,
        "hours_to_close": _finite_or_none(hours_to_close) if hours_to_close is not None else None,
        "live_chain_poll": live_chain_poll,
        "live_pin_quality": live_pin_quality,
    }


def compute_flip_result_for_chain(
    chain: pd.DataFrame,
    spot: float,
    *,
    symbol: str | None,
    asof: date | None,
    gex_inputs: GexInputs,
    dte_max: int = 1,
) -> GammaFlipResult | None:
    """Run flip search on dte cohort; None if chain empty."""
    if chain.empty or "dte" not in chain.columns:
        return None
    work = chain[chain["dte"] <= dte_max] if dte_max is not None else chain
    if work.empty:
        return None
    return compute_gamma_flip(
        work,
        spot,
        symbol=symbol,
        asof=asof,
        r=gex_inputs.r,
        q=gex_inputs.q,
        model=gex_inputs.model,
    )


def _finite_or_none(val: float) -> float | None:
    import numpy as np

    if val is None or not np.isfinite(val):
        return None
    return float(val)
