"""Shared liquidity thresholds and evidence grades (L0)."""

from __future__ import annotations

import numpy as np

from typing import Literal

Grade = Literal["A", "B", "C"]

# Single source of truth — eligible floor vs research / execution warnings.
ADV_ELIGIBLE_USD = 1_000_000
ADV_LOW_USD = 5_000_000
ADV_STRONG_USD = 20_000_000
# Amihud λ × 1e6 above this → illiquid for US large/mid caps (heuristic).
AMIHUD_HIGH = 5.0


def is_execution_risk(adv_usd: float) -> bool:
    return not np.isfinite(adv_usd) or adv_usd < ADV_LOW_USD


def grade_l0(*, adv_usd: float, amihud: float, eligible: bool) -> Grade:
    if not eligible or is_execution_risk(adv_usd):
        return "C"
    if np.isfinite(amihud) and amihud > AMIHUD_HIGH:
        return "C"
    if np.isfinite(adv_usd) and adv_usd >= ADV_STRONG_USD:
        return "A"
    return "B"
