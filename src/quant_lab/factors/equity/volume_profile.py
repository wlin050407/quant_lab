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
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        mid = float(typical.iloc[-1])
        return VolumeProfile(poc=mid, vah=mid, val=mid, total_volume=float(volume.sum()))

    counts, edges = np.histogram(typical, bins=n_bins, weights=volume)
    centers = (edges[:-1] + edges[1:]) / 2.0
    poc_idx = int(np.argmax(counts))
    poc = float(centers[poc_idx])

    order = np.argsort(-counts)
    target = float(volume.sum()) * value_area_pct
    cum = 0.0
    chosen: list[int] = []
    for idx in order:
        if counts[idx] <= 0:
            continue
        chosen.append(int(idx))
        cum += float(counts[idx])
        if cum >= target:
            break
    if not chosen:
        return VolumeProfile(
            poc=poc,
            vah=poc,
            val=poc,
            total_volume=float(volume.sum()),
        )
    chosen_centers = centers[chosen]
    return VolumeProfile(
        poc=poc,
        vah=float(np.max(chosen_centers)),
        val=float(np.min(chosen_centers)),
        total_volume=float(volume.sum()),
    )
