"""Tests for flow-adjusted effective OI."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.factors.effective_oi import (
    DEFAULT_FLOW_OI_CONFIDENCE,
    effective_open_interest,
    enrich_chain_effective_oi,
    flow_delta_from_reference,
)


def test_effective_open_interest_hand_computed() -> None:
    eff = effective_open_interest(1000.0, 500.0, confidence=0.43)
    assert eff == pytest.approx(1000.0 + 0.43 * 500.0)


def test_flow_delta_from_reference() -> None:
    chain = pd.DataFrame(
        {
            "strike": [100.0, 100.0],
            "right": ["C", "P"],
            "open_interest": [1200, 800],
        }
    )
    ref = pd.DataFrame(
        {
            "strike": [100.0, 100.0],
            "right": ["C", "P"],
            "open_interest": [1000, 1000],
        }
    )
    delta = flow_delta_from_reference(chain, ref)
    assert delta.iloc[0] == pytest.approx(200.0)
    assert delta.iloc[1] == pytest.approx(200.0)


def test_enrich_chain_adds_effective_columns() -> None:
    chain = pd.DataFrame(
        {
            "strike": [100.0],
            "right": ["C"],
            "open_interest": [1000],
            "volume": [0],
        }
    )
    ref = pd.DataFrame({"strike": [100.0], "right": ["C"], "open_interest": [800]})
    out = enrich_chain_effective_oi(chain, ref, confidence=DEFAULT_FLOW_OI_CONFIDENCE)
    assert "effective_open_interest" in out.columns
    assert out["effective_open_interest"].iloc[0] == pytest.approx(
        1000 + DEFAULT_FLOW_OI_CONFIDENCE * 200
    )
    assert out["volume"].iloc[0] > 0
    assert out["flow_source"].iloc[0] == "oi_delta"


def test_effective_open_interest_signed_can_reduce() -> None:
    eff = effective_open_interest(1000.0, -500.0, confidence=0.43, signed=True)
    assert eff == pytest.approx(1000.0 - 0.43 * 500.0)


def test_enrich_chain_signed_trade_flow() -> None:
    chain = pd.DataFrame(
        {
            "strike": [100.0],
            "right": ["C"],
            "open_interest": [1000],
            "volume": [0],
        }
    )
    signed = pd.Series([-200.0], index=chain.index)
    out = enrich_chain_effective_oi(chain, None, session_signed_flow=signed)
    assert out["flow_source"].iloc[0] == "trade_signed"
    assert out["effective_open_interest"].iloc[0] == pytest.approx(
        1000 - DEFAULT_FLOW_OI_CONFIDENCE * 200
    )


def test_enrich_chain_trade_flow_source() -> None:
    chain = pd.DataFrame(
        {
            "strike": [100.0],
            "right": ["C"],
            "open_interest": [1000],
            "volume": [0],
        }
    )
    vol = pd.Series([2500.0], index=chain.index)
    out = enrich_chain_effective_oi(chain, None, session_volume=vol)
    assert out["flow_source"].iloc[0] == "trade"
    assert out["effective_open_interest"].iloc[0] == pytest.approx(
        1000 + DEFAULT_FLOW_OI_CONFIDENCE * 2500
    )
