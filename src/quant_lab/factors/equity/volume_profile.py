"""Volume profile (POC / value area) from intraday bars."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class VolumeProfile:
    poc: float
    vah: float
    val: float
    total_volume: float


def _value_area_from_poc(
    counts: np.ndarray,
    centers: np.ndarray,
    *,
    value_area_pct: float,
    total_volume: float,
) -> tuple[float, float, float]:
    """Expand contiguously from POC until ``value_area_pct`` of volume is captured."""
    poc_idx = int(np.argmax(counts))
    poc = float(centers[poc_idx])
    if total_volume <= 0 or counts[poc_idx] <= 0:
        return poc, poc, poc

    target = total_volume * value_area_pct
    lo_idx = hi_idx = poc_idx
    cum = float(counts[poc_idx])

    while cum < target and (lo_idx > 0 or hi_idx < len(counts) - 1):
        vol_below = float(counts[lo_idx - 1]) if lo_idx > 0 else -1.0
        vol_above = float(counts[hi_idx + 1]) if hi_idx < len(counts) - 1 else -1.0
        if vol_below < 0 and vol_above < 0:
            break
        if vol_above >= vol_below:
            hi_idx += 1
            if vol_above > 0:
                cum += vol_above
        else:
            lo_idx -= 1
            if vol_below > 0:
                cum += vol_below

    return poc, float(centers[hi_idx]), float(centers[lo_idx])


def volume_profile(
    intraday: pd.DataFrame,
    *,
    n_bins: int = 24,
    value_area_pct: float = 0.70,
) -> VolumeProfile:
    """Histogram volume by typical price; POC = max volume bin center."""
    if intraday.empty or n_bins < 2:
        return VolumeProfile(
            poc=float("nan"),
            vah=float("nan"),
            val=float("nan"),
            total_volume=0.0,
        )

    typical = (
        pd.to_numeric(intraday["high"], errors="coerce")
        + pd.to_numeric(intraday["low"], errors="coerce")
        + pd.to_numeric(intraday["close"], errors="coerce")
    ) / 3.0
    volume = pd.to_numeric(intraday["volume"], errors="coerce").fillna(0.0)
    frame = pd.DataFrame({"typical": typical, "volume": volume}).dropna(subset=["typical"])
    frame = frame[np.isfinite(frame["typical"])]
    if frame.empty:
        return VolumeProfile(
            poc=float("nan"),
            vah=float("nan"),
            val=float("nan"),
            total_volume=0.0,
        )
    typical = frame["typical"]
    volume = frame["volume"]
    lo = float(typical.min())
    hi = float(typical.max())
    total_volume = float(volume.sum())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        mid = float(typical.iloc[-1])
        return VolumeProfile(poc=mid, vah=mid, val=mid, total_volume=total_volume)

    counts, edges = np.histogram(typical, bins=n_bins, weights=volume)
    centers = (edges[:-1] + edges[1:]) / 2.0
    poc, vah, val = _value_area_from_poc(
        counts,
        centers,
        value_area_pct=value_area_pct,
        total_volume=total_volume,
    )
    return VolumeProfile(
        poc=poc,
        vah=vah,
        val=val,
        total_volume=total_volume,
    )
