"""Tests for IV surface + state hub structure ingest."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_lab.terminal.iv_surface import iv_floor_strike_from_chain
from quant_lab.terminal.mm_structure import build_structure_snapshot


def _smile_chain(spot: float = 7130.0) -> pd.DataFrame:
    strikes = np.array([spot - 40, spot - 20, spot, spot + 20, spot + 40], dtype=float)
    ivs = 0.18 + 0.00008 * (strikes - spot) ** 2
    rows = []
    for k, iv in zip(strikes, ivs, strict=True):
        rows.append({"strike": k, "dte": 0, "implied_volatility": iv, "right": "C", "open_interest": 100})
        rows.append({"strike": k, "dte": 0, "implied_volatility": iv, "right": "P", "open_interest": 100})
    return pd.DataFrame(rows)


def test_iv_floor_strike_near_spot_on_symmetric_smile() -> None:
    spot = 7130.0
    floor = iv_floor_strike_from_chain(_smile_chain(spot), spot, dte_max=1)
    assert floor is not None
    assert abs(floor - spot) <= 10.0


def test_state_hubs_gamma_beats_vanna_for_primary() -> None:
    snap = build_structure_snapshot(
        terminal_symbol="^SPX",
        classic={
            "spot": 7130.0,
            "zero_gamma": 7125.0,
            "sum_gex_vol": 800000.0,
            "major_pos_vol": 7135.0,
        },
        orderflow={"spot": 7130.0},
        spot=7130.0,
        state_hubs={
            "gamma_zero": {
                "spot": 7130.0,
                "strikes": [[7135.0, 200.0, 0.0]],
            },
            "vanna_zero": {
                "spot": 7130.0,
                "strikes": [[7145.0, 400.0, 0.0]],
            },
        },
    )
    assert snap is not None
    assert snap.structure_version == "p1"
    assert snap.primary_mm_target is not None
    assert snap.primary_mm_target.level == 7135.0
