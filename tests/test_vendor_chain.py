"""Tests for vendor hybrid chain builder."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd

from quant_lab.data.vendor_chain import _contracts_to_quotes_oi, vendor_levels_from_classic


def test_contracts_to_quotes_oi_filters_0dte() -> None:
    session = date(2026, 7, 1)
    contracts = [
        {
            "option_symbol": "SPXW260701C07500000",
            "nbbo_bid": "1.0",
            "nbbo_ask": "1.2",
            "open_interest": 100,
        },
        {
            "option_symbol": "SPXW260801C07500000",
            "nbbo_bid": "10",
            "nbbo_ask": "11",
            "open_interest": 50,
        },
    ]
    quotes, oi = _contracts_to_quotes_oi(
        contracts,
        terminal_symbol="^SPX",
        session_date=session,
        spot=7500.0,
    )
    assert len(quotes) == 1
    assert float(quotes.iloc[0]["strike"]) == 7500.0
    assert int(oi.iloc[0]["open_interest"]) == 100


def test_vendor_levels_from_classic() -> None:
    levels = vendor_levels_from_classic(
        {
            "zero_gamma": 7480.0,
            "major_pos_oi": 7500.0,
            "major_neg_oi": 7450.0,
            "sum_gex_oi": 123.4,
        }
    )
    assert levels["zero_gamma"] == 7480.0
    assert levels["major_pos_oi"] == 7500.0
