"""Adjusted prices used across equity return-based factors."""

from __future__ import annotations

import pandas as pd

from quant_lab.factors.equity.relative_strength import relative_strength_vs_benchmark


def test_relative_strength_uses_adj_close() -> None:
    ticker = pd.DataFrame(
        {"close": [100.0, 50.0], "adj_close": [100.0, 100.0], "volume": [1, 1]}
    )
    bench = pd.DataFrame(
        {"close": [200.0, 200.0], "adj_close": [200.0, 200.0], "volume": [1, 1]}
    )
    rs = relative_strength_vs_benchmark(ticker, bench)
    assert rs.rs_1d == 0.0
