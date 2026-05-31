"""Regime labels and 0DTE tradeability gates (FlashAlpha-aligned).

Pure functions only — no I/O.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

RegimeLabel = Literal["long_gamma", "short_gamma", "undetermined"]
ShouldTradeReason = Literal[
    "ok",
    "no_zero_dte",
    "low_dte_gex_share",
    "low_pin_no_regime",
    "extreme_event_premium",
]


def regime_from_net_gex(net_gex: float, *, epsilon: float = 1e-6) -> RegimeLabel:
    """Map net GEX to FlashAlpha-style regime label."""
    if not np.isfinite(net_gex):
        return "undetermined"
    if net_gex > epsilon:
        return "long_gamma"
    if net_gex < -epsilon:
        return "short_gamma"
    return "undetermined"


def should_trade_zdte(
    *,
    no_zero_dte: bool = False,
    pct_gex_dte1: float,
    pin_score: float,
    regime: RegimeLabel,
    iv_ratio_0dte_7dte: float | None = None,
    min_pct_gex_dte1: float = 30.0,
    min_pin_or_regime_pin: float = 30.0,
    max_iv_ratio: float = 1.3,
) -> tuple[bool, ShouldTradeReason]:
    """FlashAlpha-style gate: is today worth trading 0DTE structures?

    See https://flashalpha.com/articles/guide-to-0dte-trading-strategies-real-time-data
    """
    if no_zero_dte:
        return False, "no_zero_dte"
    if np.isfinite(pct_gex_dte1) and pct_gex_dte1 < min_pct_gex_dte1:
        return False, "low_dte_gex_share"
    if (
        np.isfinite(pin_score)
        and pin_score < min_pin_or_regime_pin
        and regime == "undetermined"
    ):
        return False, "low_pin_no_regime"
    if iv_ratio_0dte_7dte is not None and np.isfinite(iv_ratio_0dte_7dte):
        if iv_ratio_0dte_7dte > max_iv_ratio:
            return False, "extreme_event_premium"
    return True, "ok"
