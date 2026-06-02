"""Terminal model_metadata assembly."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from quant_lab.factors.gex import compute_gamma_flip
from quant_lab.factors.rates import GexInputs
from quant_lab.terminal.model_metadata import build_model_metadata


def test_build_model_metadata_includes_dealer_sign_and_warnings() -> None:
    chain = pd.DataFrame(
        [
            {
                "strike": 100.0,
                "right": "C",
                "dte": 0,
                "implied_volatility": 0.2,
                "open_interest": 100,
            },
        ]
    )
    gex_inputs = GexInputs(
        symbol="SPX",
        r=0.05,
        q=0.013,
        model="black76",
        r_source="yaml_default",
        q_source="yaml_default",
    )
    meta = build_model_metadata(
        gex_inputs=gex_inputs,
        chain=chain,
        spot=100.0,
        hours_to_close=3.0,
        data_source="eod",
        oi_mode="settled",
        extra_warnings=["test warning"],
    )
    assert meta["dealer_sign_observed"] is False
    assert "SpotGamma" in meta["dealer_sign_assumption"]
    assert meta["time_to_expiry"]["mode"] == "hours_to_close"
    assert "test warning" in meta["data_quality_warnings"]
    assert meta["pricing_inputs"]["model"] == "black76"


def test_build_model_metadata_gamma_flip_block() -> None:
    from quant_lab.factors.gex import add_bs_gamma_column
    from tests.test_gex import _make_realistic_chain

    spot = 470.0
    chain = add_bs_gamma_column(
        _make_realistic_chain(
            spot,
            put_oi_by_strike={k: 2000 for k in [440.0, 445.0]},
            call_oi_by_strike={k: 2000 for k in [485.0, 490.0]},
        ),
        spot=spot,
    )
    flip = compute_gamma_flip(chain, spot=spot)
    gex_inputs = GexInputs(
        symbol="SPY",
        r=0.05,
        q=0.013,
        model="bs",
        r_source="yaml_default",
        q_source="yaml_default",
    )
    meta = build_model_metadata(
        gex_inputs=gex_inputs,
        chain=chain,
        spot=spot,
        data_source="eod",
        flip_result=flip,
    )
    gf = meta["gamma_flip"]
    assert gf is not None
    assert gf["primary_rule"] == "nearest_to_spot"
    assert gf["confidence"] in ("high", "medium", "low", "none")
    if not math.isnan(flip.primary_flip):
        assert gf["primary_flip"] == pytest.approx(flip.primary_flip, rel=1e-4)
