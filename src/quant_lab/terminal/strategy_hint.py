"""Strategy recommendation from regime + levels (FlashAlpha decision tree, M2 lite).

Maps positioning context to an actionable hint — not auto-trading advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

StrategyLabel = Literal[
    "sit_out",
    "pin_play",
    "gamma_fade",
    "theta_harvest",
    "breakout",
    "vol_spike_fade",
    "observe",
]


@dataclass(frozen=True)
class StrategyHint:
    label: StrategyLabel
    title: str
    summary: str
    structures: tuple[str, ...]
    confidence: Literal["high", "medium", "low"]
    sources: tuple[str, ...]


def _between_walls(spot: float, put_wall: float, call_wall: float) -> bool:
    if not all(np.isfinite(x) for x in (spot, put_wall, call_wall)):
        return False
    return put_wall < spot < call_wall


def recommend_strategy(
    *,
    regime: str,
    pin_score: float,
    spot: float,
    put_wall: float,
    call_wall: float,
    king: float,
    flip: float,
    pct_gex_dte1: float,
    should_trade: bool,
    iv_ratio: float | None = None,
    net_vex: float | None = None,
    vanna_interpretation: str | None = None,
) -> StrategyHint:
    """FlashAlpha / SpotGamma / Skylit combined hint for EoD context."""
    sources = ("FlashAlpha 5-strategy tree", "SpotGamma levels", "Skylit King/walls")

    if not should_trade:
        return StrategyHint(
            label="sit_out",
            title="Sit Out",
            summary="Gate failed — 0DTE edge unfavorable or positioning not 0DTE-driven.",
            structures=(),
            confidence="high",
            sources=sources,
        )

    if regime == "short_gamma":
        if np.isfinite(pct_gex_dte1) and pct_gex_dte1 > 50 and np.isfinite(flip):
            side = "below" if spot < flip else "above"
            return StrategyHint(
                label="breakout",
                title="Negative Gamma Breakout",
                summary=(
                    f"Short gamma + 0DTE dominates ({pct_gex_dte1:.0f}% GEX). "
                    f"Spot {side} flip — momentum / debit spreads; do NOT sell premium."
                ),
                structures=("Put/Call debit spread", "Directional on flip break"),
                confidence="medium",
                sources=sources,
            )
        return StrategyHint(
            label="sit_out",
            title="Short Gamma — Reduce Premium",
            summary="Dealers amplify moves. Avoid iron condors; wait for flip break + flow.",
            structures=(),
            confidence="high",
            sources=sources,
        )

    if regime == "long_gamma":
        if iv_ratio is not None and np.isfinite(iv_ratio) and iv_ratio > 1.0:
            vex_note = ""
            if vanna_interpretation == "vol_down_dealers_buy":
                vex_note = " Negative VEX: vol crush likely pulls dealers to buy hedges."
            return StrategyHint(
                label="vol_spike_fade",
                title="Vol Spike Fade",
                summary=(
                    "Front-end IV elevated — sell premium after event if regime stays long gamma."
                    + vex_note
                ),
                structures=("Short straddle/strangle", "IC after catalyst"),
                confidence="medium",
                sources=sources + ("VEX vanna flow",),
            )

        if (
            vanna_interpretation == "vol_down_dealers_buy"
            and net_vex is not None
            and np.isfinite(net_vex)
            and net_vex < 0
            and np.isfinite(pct_gex_dte1)
            and pct_gex_dte1 >= 40
        ):
            return StrategyHint(
                label="vol_spike_fade",
                title="Vol Crush Tailwind",
                summary=(
                    "Long gamma + negative VEX: post-event IV drop may force dealer buying, "
                    "supporting mean reversion / premium fade."
                ),
                structures=("Short straddle/strangle", "IC after catalyst"),
                confidence="low",
                sources=sources + ("VEX vanna flow",),
            )

        if np.isfinite(pin_score) and pin_score >= 70:
            king_txt = f"${king:.0f}" if np.isfinite(king) else "magnet"
            return StrategyHint(
                label="pin_play",
                title="Pin Play",
                summary=f"High pin score ({pin_score:.0f}/100) — price may gravitate toward {king_txt}.",
                structures=("ATM butterfly", "Tight iron condor @ King"),
                confidence="medium",
                sources=("Skylit King Node", "FlashAlpha pin_risk"),
            )

        if _between_walls(spot, put_wall, call_wall):
            return StrategyHint(
                label="gamma_fade",
                title="Gamma Fade / Range",
                summary="Long gamma between put/call walls — mean reversion; fade edges.",
                structures=("Iron condor @ walls", "Credit spreads at walls"),
                confidence="medium",
                sources=sources,
            )

        return StrategyHint(
            label="theta_harvest",
            title="Theta Harvest (intraday window)",
            summary="Long gamma regime — premium selling favored in 1–3 PM ET (not visible at EoD).",
            structures=("Iron condor @ walls", "Credit spreads"),
            confidence="low",
            sources=sources,
        )

    return StrategyHint(
        label="observe",
        title="Observe",
        summary="Regime undetermined — wait for clearer GEX / pin signal.",
        structures=(),
        confidence="low",
        sources=sources,
    )
