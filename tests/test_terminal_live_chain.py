"""Tests for Terminal live ThetaData chain path."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from quant_lab.data.base import OptionChainSnapshot
from quant_lab.terminal import live_chain
from quant_lab.terminal.live_chain import (
    LIVE_TIME_OF_DAY,
    _effective_time_of_day,
    clear_live_cache,
    fetch_live_intraday_chain,
    is_live_session,
)
from quant_lab.terminal.snapshot import _load_intraday_chain_safe


def _minimal_chain() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["SPXW", "SPXW"],
            "expiry": [date(2026, 5, 24), date(2026, 5, 24)],
            "strike": [5000.0, 5000.0],
            "right": ["C", "P"],
            "dte": [0, 0],
            "bid": [1.0, 1.0],
            "ask": [1.1, 1.1],
            "last_price": [1.05, 1.05],
            "implied_volatility": [0.2, 0.2],
            "volume": [10, 10],
            "open_interest": [100, 100],
            "in_the_money": [True, False],
        }
    )


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_live_cache()


def test_is_live_session_today_only() -> None:
    today = live_chain.market_today()
    assert is_live_session(today) is True
    assert is_live_session(date(2023, 7, 11)) is False


def test_effective_time_live_follows_now() -> None:
    from quant_lab.data.base import MARKET_TZ

    session = date(2026, 5, 24)
    fixed_now = datetime(2026, 5, 24, 14, 32, 15, tzinfo=MARKET_TZ)
    with patch.object(live_chain, "is_live_session", return_value=True):
        with patch.object(live_chain, "datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            assert _effective_time_of_day(session, LIVE_TIME_OF_DAY) == "14:32:15"
            assert _effective_time_of_day(session, "15:30:00") == "14:32:15"
            assert _effective_time_of_day(session, "13:00:00") == "13:00:00"


def test_resolve_intraday_clock_maps_live_on_historical_session() -> None:
    from quant_lab.terminal.live_chain import DEFAULT_PIN_PLAY_TIME, resolve_intraday_clock

    with patch.object(live_chain, "is_live_session", return_value=False):
        assert resolve_intraday_clock(date(2026, 5, 29), LIVE_TIME_OF_DAY) == DEFAULT_PIN_PLAY_TIME


def test_effective_time_caps_future_on_live_day() -> None:
    from quant_lab.data.base import MARKET_TZ

    session = date(2026, 5, 24)
    fixed_now = datetime(2026, 5, 24, 14, 30, tzinfo=MARKET_TZ)
    with patch.object(live_chain, "is_live_session", return_value=True):
        with patch.object(live_chain, "datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            assert _effective_time_of_day(session, "15:30:00") == "14:30:00"
            assert _effective_time_of_day(session, "13:00:00") == "13:00:00"


def test_fetch_live_intraday_chain_uses_cache() -> None:
    today = live_chain.market_today()
    chain = _minimal_chain()
    snapshot = OptionChainSnapshot(
        symbol="^SPX",
        asof=datetime(2026, 5, 24, 17, 0, tzinfo=timezone.utc),
        spot=5000.0,
        chain=chain,
    )

    with patch.object(live_chain, "is_live_session", return_value=True):
        with patch.object(live_chain, "_effective_time_of_day", return_value="13:00:00"):
            with patch.object(live_chain, "get_thetadata_client"):
                with patch.object(
                    live_chain, "build_0dte_chain_snapshot", return_value=snapshot
                ) as mock_build:
                    out1, spot1, time1, cached1 = fetch_live_intraday_chain(
                        today, "13:00:00", symbol="^SPX"
                    )
                    out2, spot2, time2, cached2 = fetch_live_intraday_chain(
                        today, "13:00:00", symbol="^SPX"
                    )

    assert mock_build.call_count == 1
    assert cached1 is False
    assert cached2 is True
    assert spot1 == spot2 == 5000.0
    assert time1 == time2 == "13:00:00"
    assert len(out1) == len(out2) == 2


def test_load_intraday_chain_live_vs_local() -> None:
    today = live_chain.market_today()
    live_df = pd.DataFrame({"strike": [5100.0], "open_interest": [50]})
    local_df = pd.DataFrame({"strike": [5000.0], "open_interest": [10]})
    local_meta = pd.DataFrame({"spot": [5000.0]})

    with patch.object(live_chain, "is_live_session", return_value=True):
        with patch(
            "quant_lab.terminal.snapshot.fetch_live_intraday_chain",
            return_value=(live_df, 5100.0, "13:00:00", False),
        ):
            chain, spot, time_used, source = _load_intraday_chain_safe(
                today.isoformat(), "^SPX", time_of_day="13:00:00"
            )
    assert source == "live"
    assert spot == 5100.0
    assert chain.iloc[0]["strike"] == 5100.0

    with patch.object(live_chain, "is_live_session", return_value=False):
        with patch(
            "quant_lab.terminal.snapshot.is_date_in_history_window",
            return_value=False,
        ):
            with patch(
                "quant_lab.terminal.snapshot.load_built_intraday_chain",
                return_value=(local_df, local_meta),
            ):
                chain, spot, time_used, source = _load_intraday_chain_safe(
                    "2023-07-11", "^SPX", time_of_day="13:00:00"
                )
    assert source == "local"
    assert spot == 5000.0
    assert chain.iloc[0]["strike"] == 5000.0


def test_load_intraday_chain_thetadata_when_local_missing() -> None:
    remote_df = pd.DataFrame({"strike": [5200.0], "open_interest": [80]})
    with patch.object(live_chain, "is_live_session", return_value=False):
        with patch(
            "quant_lab.terminal.snapshot.load_built_intraday_chain",
            side_effect=FileNotFoundError("missing"),
        ):
            with patch(
                "quant_lab.terminal.snapshot.is_date_in_history_window",
                return_value=True,
            ):
                with patch(
                    "quant_lab.terminal.snapshot.fetch_intraday_chain_from_thetadata",
                    return_value=(remote_df, 5200.0, "13:00:00", False),
                ):
                    chain, spot, _time_used, source = _load_intraday_chain_safe(
                        "2026-05-28", "^SPX", time_of_day="13:00:00"
                    )
    assert source == "thetadata"
    assert spot == 5200.0
    assert chain.iloc[0]["strike"] == 5200.0


def test_load_intraday_chain_prefers_remote_over_local_for_recent_session() -> None:
    """Historical sessions: remote ThetaData (chain_mode-aware) before local parquet."""
    remote_df = pd.DataFrame({"strike": [5300.0], "open_interest": [90]})
    local_df = pd.DataFrame({"strike": [5000.0], "open_interest": [10]})
    local_meta = pd.DataFrame({"spot": [5000.0]})
    with patch.object(live_chain, "is_live_session", return_value=False):
        with patch(
            "quant_lab.terminal.snapshot.is_date_in_history_window",
            return_value=True,
        ):
            with patch(
                "quant_lab.terminal.snapshot.fetch_intraday_chain_from_thetadata",
                return_value=(remote_df, 5300.0, "13:00:00", False),
            ) as mock_remote:
                with patch(
                    "quant_lab.terminal.snapshot.load_built_intraday_chain",
                    return_value=(local_df, local_meta),
                ) as mock_local:
                    chain, spot, _time_used, source = _load_intraday_chain_safe(
                        "2026-05-29", "^SPX", time_of_day="13:00:00"
                    )
    mock_remote.assert_called_once()
    mock_local.assert_not_called()
    assert source == "thetadata"
    assert spot == 5300.0
    assert chain.iloc[0]["strike"] == 5300.0


def test_load_intraday_chain_falls_back_to_local_when_remote_missing() -> None:
    local_df = pd.DataFrame({"strike": [5000.0], "open_interest": [10]})
    local_meta = pd.DataFrame({"spot": [5000.0]})
    with patch.object(live_chain, "is_live_session", return_value=False):
        with patch(
            "quant_lab.terminal.snapshot.is_date_in_history_window",
            return_value=True,
        ):
            with patch(
                "quant_lab.terminal.snapshot._fetch_thetadata_intraday_chain",
                side_effect=FileNotFoundError("no remote"),
            ):
                with patch(
                    "quant_lab.terminal.snapshot.load_built_intraday_chain",
                    return_value=(local_df, local_meta),
                ) as mock_local:
                    chain, spot, _time_used, source = _load_intraday_chain_safe(
                        "2026-05-29", "^SPX", time_of_day="13:00:00"
                    )
    mock_local.assert_called_once()
    assert source == "local"
    assert spot == 5000.0


def test_live_fail_falls_through_to_thetadata_when_local_missing() -> None:
    """After live fails, remote ThetaData is tried before local parquet."""
    today = live_chain.market_today()
    remote_df = pd.DataFrame({"strike": [5100.0], "open_interest": [50]})
    with patch.object(live_chain, "is_live_session", return_value=True):
        with patch(
            "quant_lab.terminal.snapshot.fetch_live_intraday_chain",
            side_effect=RuntimeError("theta down"),
        ):
            with patch(
                "quant_lab.terminal.snapshot.load_built_intraday_chain",
                side_effect=FileNotFoundError("no local"),
            ):
                with patch(
                    "quant_lab.terminal.snapshot.is_date_in_history_window",
                    return_value=True,
                ):
                    with patch(
                        "quant_lab.terminal.snapshot.fetch_intraday_chain_from_thetadata",
                        return_value=(remote_df, 5100.0, "13:00:00", False),
                    ) as mock_remote:
                        chain, spot, _time_used, source = _load_intraday_chain_safe(
                            today.isoformat(), "^SPX", time_of_day="live"
                        )
    mock_remote.assert_called_once()
    assert spot == 5100.0
    assert chain.iloc[0]["strike"] == 5100.0


def test_fetch_live_rejects_historical_date() -> None:
    with pytest.raises(ValueError, match="today only"):
        fetch_live_intraday_chain(date(2023, 7, 11), "13:00:00", symbol="SPY")


def test_fetch_intraday_serves_stale_cache_on_network_failure() -> None:
    """Stale-while-error: a transient ThetaData failure must serve the last good
    cached chain instead of cascading to yesterday's EoD snapshot.
    """
    from quant_lab.terminal.live_chain import fetch_intraday_chain_from_thetadata

    today = live_chain.market_today()
    chain = _minimal_chain()
    fresh_snapshot = OptionChainSnapshot(
        symbol="^SPX",
        asof=datetime(2026, 5, 24, 17, 0, tzinfo=timezone.utc),
        spot=5000.0,
        chain=chain,
    )

    with patch.object(live_chain, "is_live_session", return_value=True):
        with patch.object(live_chain, "_effective_time_of_day", return_value="13:00:00"):
            with patch.object(live_chain, "get_thetadata_client"):
                with patch.object(
                    live_chain, "build_0dte_chain_snapshot"
                ) as mock_build:
                    mock_build.return_value = fresh_snapshot
                    chain1, spot1, time1, cached1 = fetch_intraday_chain_from_thetadata(
                        today, "13:00:00", symbol="^SPX", cache_ttl_seconds=0.01
                    )
                    assert cached1 is False
                    assert spot1 == 5000.0

                    import time as _time
                    _time.sleep(0.05)

                    mock_build.reset_mock()
                    mock_build.side_effect = RuntimeError("UNAVAILABLE: gRPC blip")
                    chain2, spot2, time2, cached2 = fetch_intraday_chain_from_thetadata(
                        today, "13:00:00", symbol="^SPX", cache_ttl_seconds=0.01
                    )

    assert cached2 is True, "stale cache should be served when fetch fails"
    assert spot2 == 5000.0
    assert time2 == "13:00:00"
    assert len(chain2) == len(chain)


def test_fetch_intraday_raises_when_no_stale_cache_available() -> None:
    """First-ever fetch failure (no cache yet) must propagate — no silent recovery."""
    from quant_lab.terminal.live_chain import fetch_intraday_chain_from_thetadata

    today = live_chain.market_today()
    with patch.object(live_chain, "is_live_session", return_value=True):
        with patch.object(live_chain, "_effective_time_of_day", return_value="13:00:00"):
            with patch.object(live_chain, "get_thetadata_client"):
                with patch.object(
                    live_chain, "build_0dte_chain_snapshot",
                    side_effect=RuntimeError("UNAVAILABLE: gRPC blip"),
                ):
                    with pytest.raises(RuntimeError, match="UNAVAILABLE"):
                        fetch_intraday_chain_from_thetadata(
                            today, "13:00:00", symbol="^SPX", cache_ttl_seconds=0.01
                        )


def test_fetch_intraday_skips_stale_cache_past_max_age() -> None:
    """Stale-while-error has a ceiling: refuse to serve cache older than
    ``STALE_CACHE_MAX_SECONDS`` past TTL — propagate the real error instead.
    """
    from quant_lab.terminal import live_chain as lc
    from quant_lab.terminal.live_chain import fetch_intraday_chain_from_thetadata

    today = lc.market_today()
    chain = _minimal_chain()
    fresh_snapshot = OptionChainSnapshot(
        symbol="^SPX",
        asof=datetime(2026, 5, 24, 17, 0, tzinfo=timezone.utc),
        spot=5000.0,
        chain=chain,
    )

    with patch.object(lc, "is_live_session", return_value=True):
        with patch.object(lc, "_effective_time_of_day", return_value="13:00:00"):
            with patch.object(lc, "get_thetadata_client"):
                with patch.object(lc, "build_0dte_chain_snapshot") as mock_build:
                    mock_build.return_value = fresh_snapshot
                    fetch_intraday_chain_from_thetadata(
                        today, "13:00:00", symbol="^SPX", cache_ttl_seconds=0.01
                    )

                with patch.object(lc, "STALE_CACHE_MAX_SECONDS", 0.0):
                    import time as _time
                    _time.sleep(0.05)
                    with patch.object(
                        lc, "build_0dte_chain_snapshot",
                        side_effect=RuntimeError("UNAVAILABLE"),
                    ):
                        with pytest.raises(RuntimeError, match="UNAVAILABLE"):
                            fetch_intraday_chain_from_thetadata(
                                today, "13:00:00", symbol="^SPX", cache_ttl_seconds=0.01
                            )


def test_fetch_live_cache_isolated_by_symbol() -> None:
    today = live_chain.market_today()
    chain_spx = _minimal_chain()
    chain_spy = chain_spx.copy()
    chain_spy["symbol"] = "SPY"

    with patch.object(live_chain, "is_live_session", return_value=True):
        with patch.object(live_chain, "_effective_time_of_day", return_value="13:00:00"):
            with patch.object(live_chain, "get_thetadata_client"):
                with patch.object(live_chain, "build_0dte_chain_snapshot") as mock_build:
                    mock_build.side_effect = [
                        OptionChainSnapshot(
                            symbol="^SPX",
                            asof=datetime(2026, 5, 24, 17, 0, tzinfo=timezone.utc),
                            spot=5000.0,
                            chain=chain_spx,
                        ),
                        OptionChainSnapshot(
                            symbol="SPY",
                            asof=datetime(2026, 5, 24, 17, 0, tzinfo=timezone.utc),
                            spot=500.0,
                            chain=chain_spy,
                        ),
                    ]
                    fetch_live_intraday_chain(today, "13:00:00", symbol="^SPX")
                    fetch_live_intraday_chain(today, "13:00:00", symbol="SPY")

    assert mock_build.call_count == 2
