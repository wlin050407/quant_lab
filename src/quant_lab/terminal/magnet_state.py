"""Session-scoped magnet (King) shift tracking for live Terminal."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_magnet_by_session: dict[tuple[str, str], float] = {}


@dataclass(frozen=True)
class MagnetShift:
    """King strike moved since the previous live poll."""

    previous: float
    current: float
    delta_pts: float


def record_magnet_shift(
    symbol: str,
    session_iso: str,
    king: float | None,
) -> MagnetShift | None:
    """Update stored King; return shift metadata when strike changed."""
    key = (symbol, session_iso)
    prev = _magnet_by_session.get(key)
    if king is None or not np.isfinite(king):
        return None
    current = float(king)
    _magnet_by_session[key] = current
    if prev is None or not np.isfinite(prev):
        return None
    if abs(current - prev) < 0.01:
        return None
    return MagnetShift(previous=float(prev), current=current, delta_pts=current - float(prev))


def clear_magnet_state() -> None:
    """Reset in-memory state (tests)."""
    _magnet_by_session.clear()
