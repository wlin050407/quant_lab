"""Cross-index structural alignment (Skylit Trinity Mode).

Compares dealer positioning levels across SPX / SPY / QQQ (and proxies) to
score whether the "structural story" is coherent before committing size.

No I/O — callers supply per-symbol spot and structural level (typically King).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np

TrinityDirection = Literal["support", "resistance", "mixed", "insufficient_data"]

# SPX notional ≈ 10× SPY; strike grids differ but fractional distance from spot
# should agree when dealers are positioned coherently.
SPX_TO_SPY_STRIKE_RATIO = 10.0


@dataclass(frozen=True)
class TrinityAlignment:
    """Result of a cross-index level alignment check."""

    score: float
    direction: TrinityDirection
    n_symbols: int
    distance_pcts: dict[str, float]


def level_distance_pct(spot: float, level: float) -> float:
    """Signed fractional distance from spot to structural level."""
    if not np.isfinite(spot) or spot <= 0 or not np.isfinite(level):
        return float("nan")
    return float((level - spot) / spot)


def spx_strike_to_spy_equivalent(spx_strike: float) -> float:
    """Convert SPX index strike to approximate SPY strike (notional proxy)."""
    return float(spx_strike / SPX_TO_SPY_STRIKE_RATIO)


def trinity_score(
    entries: Sequence[tuple[str, float, float]],
    *,
    tolerance_pct: float = 0.008,
    min_symbols: int = 2,
) -> TrinityAlignment:
    """Score 0–100 alignment across multiple index levels.

    Args:
        entries: sequence of ``(symbol, spot, structural_level)`` e.g. King node.
        tolerance_pct: max std of distance_pcts for a perfect 100 score.
        min_symbols: require at least this many valid entries.

    Returns:
        ``TrinityAlignment`` with score, direction, and per-symbol distances.
    """
    distances: dict[str, float] = {}
    for symbol, spot, level in entries:
        d = level_distance_pct(spot, level)
        if np.isfinite(d):
            distances[symbol] = d

    n = len(distances)
    if n < min_symbols:
        return TrinityAlignment(
            score=float("nan"),
            direction="insufficient_data",
            n_symbols=n,
            distance_pcts=distances,
        )

    vals = np.array(list(distances.values()), dtype="float64")
    signs = np.sign(vals)
    if np.all(signs > 0):
        direction: TrinityDirection = "resistance"
    elif np.all(signs < 0):
        direction = "support"
    else:
        direction = "mixed"

    std = float(np.std(vals))
    if direction == "mixed":
        score = float(np.clip(50.0 * (1.0 - std / tolerance_pct), 0.0, 50.0))
    else:
        score = float(np.clip(100.0 * (1.0 - std / tolerance_pct), 0.0, 100.0))

    return TrinityAlignment(
        score=score,
        direction=direction,
        n_symbols=n,
        distance_pcts=distances,
    )


def trinity_from_kings(
    *,
    spy: tuple[float, float] | None = None,
    spx: tuple[float, float] | None = None,
    qqq: tuple[float, float] | None = None,
    tolerance_pct: float = 0.008,
) -> TrinityAlignment:
    """Convenience wrapper: ``(spot, king_strike)`` per symbol."""
    entries: list[tuple[str, float, float]] = []
    if spy is not None:
        entries.append(("SPY", spy[0], spy[1]))
    if spx is not None:
        entries.append(("SPX", spx[0], spx[1]))
    if qqq is not None:
        entries.append(("QQQ", qqq[0], qqq[1]))
    return trinity_score(entries, tolerance_pct=tolerance_pct)
