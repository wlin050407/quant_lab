"""Non-option baseline strategies for backtest engine validation."""

from __future__ import annotations

import pandas as pd


def zscore_mean_reversion_signals(
    close: pd.Series,
    *,
    window: int = 5,
    scale_z: float = 1.0,
) -> pd.Series:
    """Rolling Z-score mean reversion: short positive Z, long negative Z.

    Args:
        close: close price series.
        window: lookback for mean / std.
        scale_z: divide Z by this before clipping to [-1, 1].

    Returns:
        Target weight series aligned to ``close.index``.
    """
    if window <= 1:
        raise ValueError("window must be > 1")
    if scale_z <= 0:
        raise ValueError("scale_z must be positive")

    ma = close.rolling(window).mean()
    std = close.rolling(window).std()
    z = (close - ma) / std
    signal = (-z / scale_z).clip(-1.0, 1.0)
    return signal.fillna(0.0)
