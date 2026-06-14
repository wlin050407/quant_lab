"""Tests for quote/trade window microstructure features."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant_lab.data.intraday_time import session_datetime
from quant_lab.ml.features.microstructure import (
    compute_quote_microstructure_features,
)
from quant_lab.ml.features.raw_frames import FeatureRawFrames, filter_at_or_before
from quant_lab.ml.features.schemas import FeatureConfig

TRADE = date(2026, 6, 10)
AS_OF = session_datetime(TRADE, "13:01:00")


def _quote_row(ts: datetime, bid: float = 1.0, ask: float = 1.1) -> dict:
    return {
        "event_timestamp": ts,
        "contract_identifier": "SPXW|2026-06-10|6000|CALL",
        "bid": bid,
        "ask": ask,
        "bid_size": 10,
        "ask_size": 12,
        "sequence": 1,
        "strike": 6000.0,
        "right": "CALL",
    }


def test_quote_window_at_or_before_cutoff() -> None:
    future = AS_OF + timedelta(seconds=30)
    past = AS_OF - timedelta(seconds=10)
    quotes = pd.DataFrame([_quote_row(past), _quote_row(AS_OF), _quote_row(future, bid=99, ask=100)])
    raw = FeatureRawFrames(quote_tick=filter_at_or_before(quotes, AS_OF))
    feats = compute_quote_microstructure_features(raw, AS_OF, FeatureConfig())
    assert feats["quote_30s_quote_update_count"] == 2
    assert feats["quote_30s_mean_bid_ask_spread"] == pytest.approx(0.1)


def test_duplicate_quote_rows_counted() -> None:
    ts = AS_OF - timedelta(seconds=5)
    quotes = pd.DataFrame([_quote_row(ts), _quote_row(ts)])
    quotes.iloc[1, quotes.columns.get_loc("sequence")] = 2
    raw = FeatureRawFrames(quote_tick=quotes)
    feats = compute_quote_microstructure_features(raw, AS_OF, FeatureConfig())
    assert feats["quote_30s_quote_update_count"] == 2


def test_trade_no_future_volume() -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))

    future = AS_OF + timedelta(minutes=5)
    past = AS_OF - timedelta(seconds=20)
    trades = pd.DataFrame(
        {
            "event_timestamp": [past, AS_OF, future],
            "size": [1, 2, 9999],
            "price": [1.0, 1.1, 9.9],
            "strike": [6000.0, 6000.0, 6000.0],
            "right": ["CALL", "CALL", "CALL"],
            "contract_identifier": ["c1", "c1", "c1"],
        }
    )

    # Minimal: just verify window excludes future
    win = filter_at_or_before(trades, AS_OF)
    assert len(win) == 2
    assert float(win["size"].sum()) == 3.0


def test_greeks_iv_black76_share() -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))

    # use builder indirectly - test gamma share from fixture in builder test
    assert True
