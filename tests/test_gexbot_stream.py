"""Tests for GEXBot stream helpers (no live WebSocket)."""

from __future__ import annotations

from quant_lab.data.gexbot_stream import (
    _hub_for_group,
    _ticker_from_group,
    default_ws_groups,
)
from quant_lab.data.vendor_chain import vendor_pin_ladder_from_classic


def test_hub_and_ticker_from_group() -> None:
    assert _hub_for_group("SPX_classic_gex_zero") == "classic"
    assert _hub_for_group("SPX_orderflow_orderflow") == "orderflow"
    assert _ticker_from_group("SPX_classic_gex_zero") == "SPX"
    assert _ticker_from_group("ES_SPX_orderflow_orderflow") == "ES_SPX"


def test_default_ws_groups_contains_spx() -> None:
    groups = default_ws_groups()
    assert "SPX_classic_gex_zero" in groups


def test_vendor_pin_ladder_normalizes_weights() -> None:
    classic = {
        "max_priors": [
            [7135.0, 1000.0],
            [7135.0, 500.0],
            [7140.0, 200.0],
        ]
    }
    ladder = vendor_pin_ladder_from_classic(classic, top_n=2)
    assert len(ladder) == 2
    assert ladder[0]["strike"] == 7135.0
    assert ladder[0]["weight"] == 1500.0
    assert ladder[0]["weight_norm"] == 1.0
    assert ladder[1]["strike"] == 7140.0
    assert ladder[1]["weight_norm"] < 1.0
