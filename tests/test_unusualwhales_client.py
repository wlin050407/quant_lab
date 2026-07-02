"""Tests for Unusual Whales OCC parsing and client helpers."""

from __future__ import annotations

from datetime import date

import pytest

from quant_lab.data.unusualwhales_client import parse_occ_option_symbol, uw_ticker


def test_parse_spxw_occ_symbol() -> None:
    root, expiry, right, strike = parse_occ_option_symbol("SPXW260701C07500000")
    assert root == "SPXW"
    assert expiry == date(2026, 7, 1)
    assert right == "C"
    assert strike == 7500.0


def test_parse_spy_occ_symbol() -> None:
    root, expiry, right, strike = parse_occ_option_symbol("SPY260701C00480000")
    assert root == "SPY"
    assert expiry == date(2026, 7, 1)
    assert right == "C"
    assert strike == 480.0


def test_uw_ticker_normalizes_caret() -> None:
    assert uw_ticker("^SPX") == "SPX"


def test_parse_invalid_symbol_raises() -> None:
    with pytest.raises(ValueError):
        parse_occ_option_symbol("not-a-symbol")
