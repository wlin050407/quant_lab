"""Shared liquidity thresholds and evidence grades (L0)."""

from __future__ import annotations

import numpy as np

from typing import Literal

Grade = Literal["A", "B", "C"]

# Single source of truth — eligible floor vs research / execution warnings.
ADV_ELIGIBLE_USD = 1_000_000
ADV_LOW_USD = 5_000_000
ADV_STRONG_USD = 20_000_000
# Fallback when percentile history is too short (micro / thin names).
AMIHUD_FALLBACK_HIGH = 1.0


def is_execution_risk(adv_usd: float) -> bool:
    return not np.isfinite(adv_usd) or adv_usd < ADV_LOW_USD


def is_amihud_elevated(amihud: float, *, amihud_threshold: float) -> bool:
    if not np.isfinite(amihud):
        return False
    if np.isfinite(amihud_threshold):
        return amihud > amihud_threshold
    return amihud > AMIHUD_FALLBACK_HIGH


def grade_l0(
    *,
    adv_usd: float,
    amihud: float,
    eligible: bool,
    amihud_threshold: float = float("nan"),
) -> Grade:
    if not eligible or is_execution_risk(adv_usd):
        return "C"
    if is_amihud_elevated(amihud, amihud_threshold=amihud_threshold):
        return "C"
    if np.isfinite(adv_usd) and adv_usd >= ADV_STRONG_USD:
        return "A"
    return "B"


def liquidity_module_score(
    *,
    eligible: bool,
    adv_usd: float,
    amihud: float,
    amihud_threshold: float = float("nan"),
) -> float:
    """Shared L0 score for module bias and weakest-link consistency."""
    if not eligible or is_execution_risk(adv_usd):
        return -0.35
    if is_amihud_elevated(amihud, amihud_threshold=amihud_threshold):
        return -0.2
    if np.isfinite(adv_usd) and adv_usd >= ADV_STRONG_USD:
        return 0.08
    return 0.0
