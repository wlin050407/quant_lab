"""Shared daily price series for equity factors (split-adjusted when available)."""

from __future__ import annotations

import pandas as pd


def uses_adjusted_close(daily: pd.DataFrame) -> bool:
    """True when ``adj_close`` is present and mostly populated."""
    if daily.empty or "adj_close" not in daily.columns:
        return False
    adj = pd.to_numeric(daily["adj_close"], errors="coerce")
    need = max(2, min(3, len(daily)))
    return int(adj.notna().sum()) >= need


def price_series_for_returns(daily: pd.DataFrame) -> pd.Series:
    """Split-adjusted close when available; else raw close."""
    if uses_adjusted_close(daily):
        return pd.to_numeric(daily["adj_close"], errors="coerce")
    return pd.to_numeric(daily["close"], errors="coerce")
