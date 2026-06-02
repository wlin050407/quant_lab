"""Equity liquidity uses split-adjusted prices when available."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_lab.factors.equity.liquidity import amihud_illiquidity, uses_adjusted_close


def test_amihud_uses_adj_close_after_split() -> None:
    """Raw close jump on split day; adj_close should keep returns stable."""
    daily = pd.DataFrame(
        {
            "close": [100.0, 50.0, 50.5],
            "adj_close": [100.0, 100.0, 100.5],
            "volume": [1_000_000, 1_000_000, 1_000_000],
        }
    )
    assert uses_adjusted_close(daily)
    adj_illiq = amihud_illiquidity(daily)
    raw_only = daily.drop(columns=["adj_close"])
    raw_illiq = amihud_illiquidity(raw_only)
    assert np.isfinite(adj_illiq)
    assert np.isfinite(raw_illiq)
    assert raw_illiq > adj_illiq
