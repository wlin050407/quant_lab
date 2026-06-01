"""Tests for Lee-Ready signed flow aggregation."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.factors.trade_flow import (
    aggregate_signed_flow,
    classify_lee_ready,
    classify_tick_rule,
)


def test_classify_lee_ready_at_ask() -> None:
    assert classify_lee_ready(1.05, 1.00, 1.05) == 1


def test_classify_lee_ready_at_bid() -> None:
    assert classify_lee_ready(1.00, 1.00, 1.05) == -1


def test_classify_tick_rule_uptick() -> None:
    assert classify_tick_rule(2.0, 1.9) == 1
    assert classify_tick_rule(1.8, 1.9) == -1


def test_aggregate_signed_flow_net_buy() -> None:
    trades = pd.DataFrame(
        {
            "strike": [100.0, 100.0, 100.0],
            "right": ["C", "C", "C"],
            "price": [1.05, 1.05, 1.05],
            "size": [10, 20, 5],
            "ms_of_day": [1, 2, 3],
        }
    )
    quotes = pd.DataFrame(
        {
            "strike": [100.0],
            "right": ["C"],
            "bid": [1.00],
            "ask": [1.05],
            "ms_of_day": [0],
        }
    )
    out = aggregate_signed_flow(trades, quotes)
    assert len(out) == 1
    assert out["volume"].iloc[0] == pytest.approx(35.0)
    assert out["signed_flow"].iloc[0] == pytest.approx(35.0)


def test_aggregate_signed_flow_net_sell_reduces() -> None:
    trades = pd.DataFrame(
        {
            "strike": [100.0, 100.0, 100.0],
            "right": ["P", "P", "P"],
            "price": [1.00, 1.00, 1.05],
            "size": [10, 10, 10],
            "ms_of_day": [1, 2, 3],
        }
    )
    quotes = pd.DataFrame(
        {
            "strike": [100.0],
            "right": ["P"],
            "bid": [1.00],
            "ask": [1.05],
            "ms_of_day": [0],
        }
    )
    out = aggregate_signed_flow(trades, quotes)
    assert out["volume"].iloc[0] == pytest.approx(30.0)
    assert out["signed_flow"].iloc[0] == pytest.approx(-10.0)
