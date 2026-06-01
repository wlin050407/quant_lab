"""Tests for ThetaData intraday fetch helpers (no network).

Covers the perf-critical de-duplication fix: ``build_0dte_chain_snapshot``
used to fire two cascading calls (``signed_flow → cumulative_volume``) which
re-pulled the heavy full-session 1m quote window twice on Value-tier paths.
The new ``fetch_0dte_session_flow_at_time`` does it in a single trades +
single quotes pull.

Also covers ``fetch_0dte_chain_at_time``'s integral-time window fix — the old
``end_dt.replace(minute=max(0, m-1))`` collapsed to zero length at ``13:00:00``.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd

from quant_lab.data.thetadata_intraday import (
    fetch_0dte_chain_at_time,
    fetch_0dte_cumulative_volume_at_time,
    fetch_0dte_session_flow_at_time,
    fetch_0dte_signed_flow_at_time,
)


def _trades_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strike": [5900.0, 5900.0, 5910.0],
            "right": ["C", "P", "C"],
            "price": [1.20, 0.80, 0.75],
            "size": [10.0, 5.0, 3.0],
            "ms_of_day": [
                10 * 3600 * 1000,
                11 * 3600 * 1000,
                12 * 3600 * 1000,
            ],
        }
    )


def _quotes_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strike": [5900.0, 5900.0, 5910.0],
            "right": ["C", "P", "C"],
            "bid": [1.18, 0.78, 0.73],
            "ask": [1.22, 0.82, 0.77],
            "ms_of_day": [
                10 * 3600 * 1000 - 1000,
                11 * 3600 * 1000 - 1000,
                12 * 3600 * 1000 - 1000,
            ],
        }
    )


def test_session_flow_makes_one_trades_and_one_quotes_call() -> None:
    """The dedup fix: a single full-session pass for both trades and quotes."""
    client = MagicMock()
    client.option_history_trade.return_value = _trades_df()
    client.option_history_quote.return_value = _quotes_df()

    out = fetch_0dte_session_flow_at_time(
        client,
        session_date=date(2026, 5, 29),
        time_of_day="13:00:00",
        option_root="SPXW",
        strike_range=80,
    )

    assert client.option_history_trade.call_count == 1, (
        "session_flow must pull trades exactly once (was 2-3 in old cascade)"
    )
    assert client.option_history_quote.call_count == 1, (
        "session_flow must pull session quotes exactly once (was 2 in old cascade)"
    )
    assert not out.empty
    assert "signed_flow" in out.columns
    assert "volume" in out.columns


def test_session_flow_empty_trades_skips_quote_pull() -> None:
    """Value tier (no trade history) must not pay for the heavy quotes call."""
    client = MagicMock()
    client.option_history_trade.return_value = pd.DataFrame()

    out = fetch_0dte_session_flow_at_time(
        client,
        session_date=date(2026, 5, 29),
        time_of_day="13:00:00",
        option_root="SPXW",
    )

    assert client.option_history_trade.call_count == 1
    assert client.option_history_quote.call_count == 0, (
        "no trades → no need to pull session quotes for Lee-Ready signing"
    )
    assert out.empty
    assert list(out.columns) == ["strike", "right", "signed_flow", "volume"]


def test_session_flow_falls_back_to_unsigned_when_signing_fails() -> None:
    """If Lee-Ready aggregation errors, return unsigned volume from same trades — no re-fetch."""
    client = MagicMock()
    client.option_history_trade.return_value = _trades_df()
    # Quotes frame missing required ``bid``/``ask`` columns triggers ValueError
    # inside ``aggregate_signed_flow._prepare_quotes``.
    client.option_history_quote.return_value = pd.DataFrame(
        {
            "strike": [5900.0],
            "right": ["C"],
            "ms_of_day": [10 * 3600 * 1000],
        }
    )

    out = fetch_0dte_session_flow_at_time(
        client,
        session_date=date(2026, 5, 29),
        time_of_day="13:00:00",
        option_root="SPXW",
    )

    assert client.option_history_trade.call_count == 1
    assert client.option_history_quote.call_count == 1, (
        "must not re-pull quotes after signing fails"
    )
    assert not out.empty
    assert "volume" in out.columns
    assert "signed_flow" not in out.columns, (
        "unsigned fallback should not carry a signed_flow column"
    )


def test_cumulative_volume_no_longer_calls_signed_flow_internally() -> None:
    """The pre-fix bug: ``cumulative_volume`` re-pulled trades AND quotes through
    ``signed_flow``. Now it pulls trades exactly once.
    """
    client = MagicMock()
    client.option_history_trade.return_value = _trades_df()
    client.option_history_quote.return_value = _quotes_df()

    out = fetch_0dte_cumulative_volume_at_time(
        client,
        session_date=date(2026, 5, 29),
        time_of_day="13:00:00",
        option_root="SPXW",
    )

    assert client.option_history_trade.call_count == 1
    assert client.option_history_quote.call_count == 0, (
        "cumulative_volume only needs trades — must not pull session quotes"
    )
    assert not out.empty
    assert list(out.columns) == ["strike", "right", "volume"]


def test_signed_flow_at_time_still_pulls_quotes_for_signing() -> None:
    """The legacy ``fetch_0dte_signed_flow_at_time`` retains its 1 trades + 1 quotes pattern."""
    client = MagicMock()
    client.option_history_trade.return_value = _trades_df()
    client.option_history_quote.return_value = _quotes_df()

    out = fetch_0dte_signed_flow_at_time(
        client,
        session_date=date(2026, 5, 29),
        time_of_day="13:00:00",
        option_root="SPXW",
    )

    assert client.option_history_trade.call_count == 1
    assert client.option_history_quote.call_count == 1
    assert "signed_flow" in out.columns


def test_chain_at_time_window_does_not_collapse_at_integral_minute() -> None:
    """Old bug: ``end_dt.replace(minute=max(0, m-1))`` made start==end at ``HH:00``.

    Pin-play times are 10:00 / 13:00 / 15:30 — the first two hit the bug
    and silently returned an empty window. The fix uses ``timedelta(minutes=1)``
    so the hour rolls over.
    """
    client = MagicMock()
    client.option_history_quote.return_value = pd.DataFrame(
        {
            "strike": [5900.0],
            "right": ["C"],
            "bid": [1.0],
            "ask": [1.1],
            "timestamp": ["2026-05-29T13:00:00"],
        }
    )

    fetch_0dte_chain_at_time(
        client,
        session_date=date(2026, 5, 29),
        time_of_day="13:00:00",
        option_root="SPXW",
    )

    assert client.option_history_quote.call_count == 1
    _, kwargs = client.option_history_quote.call_args
    assert kwargs["start_time"] == "12:59:00", (
        f"expected 12:59:00 start, got {kwargs['start_time']} — window collapsed"
    )
    assert kwargs["end_time"] == "13:00:00"


def test_chain_at_time_clamps_start_to_session_open() -> None:
    """At 09:30 the start must not slip to 09:29 (pre-open, ThetaData errors)."""
    client = MagicMock()
    client.option_history_quote.return_value = pd.DataFrame()

    fetch_0dte_chain_at_time(
        client,
        session_date=date(2026, 5, 29),
        time_of_day="09:30:00",
        option_root="SPXW",
    )

    _, kwargs = client.option_history_quote.call_args
    assert kwargs["start_time"] == "09:30:00"
    assert kwargs["end_time"] == "09:30:00"


def test_pin_chain_mode_uses_oi_delta_not_session_flow() -> None:
    """``pin`` enriches from 09:30 OI reference without trade-tape pulls."""
    from unittest.mock import patch

    from zoneinfo import ZoneInfo

    from quant_lab.data.thetadata_chain import build_0dte_chain_snapshot
    from quant_lab.factors.effective_oi import EFFECTIVE_OI_COL, FLOW_SOURCE_COL

    et = ZoneInfo("America/New_York")
    quotes = pd.DataFrame(
        {
            "strike": [5900.0, 5900.0],
            "right": ["C", "P"],
            "bid": [1.0, 0.9],
            "ask": [1.1, 1.0],
            "timestamp": pd.to_datetime(
                ["2026-05-29 13:00:00", "2026-05-29 13:00:00"],
            ).tz_localize(et),
        }
    )
    oi_history = pd.DataFrame(
        {
            "strike": [5900.0, 5900.0, 5900.0, 5900.0],
            "right": ["C", "P", "C", "P"],
            "open_interest": [100, 80, 150, 90],
            "timestamp": pd.to_datetime(
                [
                    "2026-05-29 09:30:00",
                    "2026-05-29 09:30:00",
                    "2026-05-29 13:00:00",
                    "2026-05-29 13:00:00",
                ],
            ).tz_localize(et),
        }
    )

    client = MagicMock()
    with (
        patch(
            "quant_lab.data.thetadata_chain.fetch_0dte_chain_at_time",
            return_value=quotes,
        ),
        patch(
            "quant_lab.data.thetadata_chain.fetch_0dte_open_interest_history",
            return_value=oi_history,
        ),
        patch(
            "quant_lab.data.thetadata_chain.fetch_0dte_session_flow_at_time",
        ) as mock_flow,
        patch(
            "quant_lab.data.thetadata_chain._fetch_underlying_spot",
            return_value=5900.0,
        ),
    ):
        snap = build_0dte_chain_snapshot(
            client,
            session_date=date(2026, 5, 29),
            time_of_day="13:00:00",
            chain_mode="pin",
        )

    mock_flow.assert_not_called()
    chain = snap.chain
    assert EFFECTIVE_OI_COL in chain.columns
    assert (chain[FLOW_SOURCE_COL] == "oi_delta").all()
    call_eff = int(chain.loc[chain["right"] == "C", EFFECTIVE_OI_COL].iloc[0])
    assert call_eff == 172  # 150 + round(0.43 * |150 - 100|)
