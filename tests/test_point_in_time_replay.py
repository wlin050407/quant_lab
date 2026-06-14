"""Tests for point-in-time replay engine (ML-P4)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from quant_lab.data.intraday_lake import (
    PILOT_LAKE_ROOT,
    build_derived_gamma_black76,
    build_session_metadata_row,
    ingest_partition,
    normalize_index_price,
    normalize_option_greeks,
    normalize_option_open_interest,
    normalize_option_quote,
    normalize_option_trade,
    partition_dir,
)
from quant_lab.data.intraday_manifest import manifest_path
from quant_lab.data.intraday_time import session_datetime
from quant_lab.data.point_in_time_replay import (
    ReplayRequest,
    compute_state_hash,
    default_pilot_data_root,
    replay_state,
    to_gex_adapter_frame,
)
from quant_lab.data.replay_integrity import MissingManifestError

TRADE = date(2026, 6, 10)
ROOT = "SPXW"
CID = f"{ROOT}|{TRADE.isoformat()}|6000.0|CALL"
AS_OF = session_datetime(TRADE, "13:01:00")


def _ts(hms: str) -> str:
    return f"2026-06-10T{hms}"


def _build_fixture_lake(tmp_path: Path, *, adversarial: bool = False) -> Path:
    """Minimal lake with one contract and optional future leakage rows."""
    req = "fixture-req"
    quotes = pd.DataFrame(
        {
            "timestamp": [_ts("13:00:00"), _ts("13:00:30"), _ts("13:02:00")],
            "expiration": [TRADE, TRADE, TRADE],
            "strike": [6000.0, 6000.0, 6000.0],
            "right": ["CALL", "CALL", "CALL"],
            "bid": [1.0, 1.5, 999.0],
            "ask": [1.1, 1.6, 999.9],
            "bid_size": [10, 11, 99],
            "ask_size": [12, 13, 99],
            "sequence": [1, 2, 3],
        }
    )
    trades = pd.DataFrame(
        {
            "timestamp": [_ts("13:00:10"), _ts("13:01:30"), _ts("13:05:00")],
            "expiration": [TRADE, TRADE, TRADE],
            "strike": [6000.0, 6000.0, 6000.0],
            "right": ["CALL", "CALL", "CALL"],
            "price": [1.05, 1.55, 9.99],
            "size": [1, 2, 99],
            "exchange": [1, 1, 1],
            "condition": [0, 0, 0],
            "sequence": [10, 11, 12],
        }
    )
    greeks = pd.DataFrame(
        {
            "timestamp": [_ts("13:00:00"), _ts("13:01:00"), _ts("13:03:00")],
            "expiration": [TRADE, TRADE, TRADE],
            "strike": [6000.0, 6000.0, 6000.0],
            "right": ["CALL", "CALL", "CALL"],
            "implied_vol": [0.15, 0.16, 0.99],
            "delta": [0.5, 0.51, 0.99],
            "theta": [-1.0, -1.1, -9.9],
            "vega": [0.2, 0.21, 9.9],
            "rho": [0.01, 0.01, 0.99],
            "underlying_price": [6000.0, 6001.0, 9999.0],
        }
    )
    oi = pd.DataFrame(
        {
            "timestamp": [_ts("06:30:00"), _ts("13:10:00")],
            "expiration": [TRADE, TRADE],
            "strike": [6000.0, 6000.0],
            "right": ["CALL", "CALL"],
            "open_interest": [100, 99999],
        }
    )
    index = pd.DataFrame(
        {
            "timestamp": [_ts("13:00:00"), _ts("13:01:00"), _ts("13:05:00")],
            "price": [6000.0, 6001.0, 9999.0],
        }
    )
    if not adversarial:
        quotes = quotes.iloc[:2]
        trades = trades.iloc[:2]
        greeks = greeks.iloc[:2]
        oi = oi.iloc[:1]
        index = index.iloc[:2]

    ingest_partition(
        normalize_option_quote(
            quotes, dataset="option_quote_tick", root=ROOT, trade_date=TRADE,
            source_endpoint="option_history_quote", source_request_id=req,
        ),
        lake_root=tmp_path, dataset="option_quote_tick", trade_date=TRADE,
        root=ROOT, expiration=TRADE,
    )
    ingest_partition(
        normalize_option_quote(
            quotes, dataset="option_quote_1s", root=ROOT, trade_date=TRADE,
            source_endpoint="option_history_quote", source_request_id=req,
        ),
        lake_root=tmp_path, dataset="option_quote_1s", trade_date=TRADE,
        root=ROOT, expiration=TRADE,
    )
    ingest_partition(
        normalize_option_trade(
            trades, root=ROOT, trade_date=TRADE,
            source_endpoint="option_history_trade", source_request_id=req,
        ),
        lake_root=tmp_path, dataset="option_trade_tick", trade_date=TRADE,
        root=ROOT, expiration=TRADE,
    )
    gdf = normalize_option_greeks(
        greeks, root=ROOT, trade_date=TRADE,
        source_endpoint="option_history_greeks_first_order", source_request_id=req,
    )
    ingest_partition(
        gdf, lake_root=tmp_path, dataset="option_greeks_1m_first_order",
        trade_date=TRADE, root=ROOT, expiration=TRADE,
    )
    from unittest.mock import patch

    with patch("quant_lab.data.intraday_lake.resolve_gex_inputs") as mock_inputs:
        mock_inputs.return_value = type("R", (), {"r": 0.04, "q": 0.0})()
        gamma = build_derived_gamma_black76(gdf, trade_date=TRADE, root=ROOT)
    ingest_partition(
        gamma, lake_root=tmp_path, dataset="derived_gamma_black76_1m",
        trade_date=TRADE, root=ROOT, expiration=TRADE,
    )
    ingest_partition(
        normalize_option_open_interest(
            oi, root=ROOT, trade_date=TRADE, requested_date=TRADE,
            source_endpoint="option_history_open_interest", source_request_id=req,
        ),
        lake_root=tmp_path, dataset="option_open_interest", trade_date=TRADE,
        root=ROOT, expiration=TRADE,
    )
    ingest_partition(
        normalize_index_price(
            index, dataset="index_price_tick", symbol="SPX", trade_date=TRADE,
            source_endpoint="index_history_price", source_request_id=req,
        ),
        lake_root=tmp_path, dataset="index_price_tick", trade_date=TRADE, symbol="SPX",
    )
    ingest_partition(
        build_session_metadata_row(
            trade_date=TRADE, root=ROOT, symbol="SPX", strike_range=2,
            window_start="13:00:00", window_end="13:02:00",
            quote_interval="tick", pilot_label="test-fixture",
        ),
        lake_root=tmp_path, dataset="session_metadata", trade_date=TRADE, root=ROOT,
    )
    return tmp_path


def _replay(tmp_path: Path, as_of: datetime = AS_OF, **kwargs: object):
    return replay_state(
        TRADE,
        as_of,
        root=ROOT,
        expiration=TRADE,
        data_root=tmp_path,
        **kwargs,
    )


def test_latest_quote_at_and_between_events(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    exact = _replay(lake, session_datetime(TRADE, "13:00:30"))
    row = exact.option_chain.iloc[0]
    assert row["latest_bid"] == 1.5
    assert row["quote_source_dataset"] == "option_quote_tick"

    between = _replay(lake, session_datetime(TRADE, "13:00:45"))
    assert between.option_chain.iloc[0]["latest_bid"] == 1.5


def test_quote_before_first_event_missing(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    state = _replay(lake, session_datetime(TRADE, "12:59:00"))
    flags = state.option_chain.iloc[0]["data_quality_flags"]
    assert "missing_quote" in flags


def test_timestamp_equals_event_included(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    state = _replay(lake, session_datetime(TRADE, "13:00:30"))
    assert state.option_chain.iloc[0]["latest_bid"] == 1.5


def test_trade_cumulative_not_full_day(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    state = _replay(lake, session_datetime(TRADE, "13:02:00"))
    row = state.option_chain.iloc[0]
    assert row["cumulative_trade_count"] == 2
    assert row["last_trade_price"] == 1.55
    assert row["trade_notional_proxy"] == pytest.approx((1.05 * 1 + 1.55 * 2) * 100)


def test_greek_and_gamma_latest_at_or_before(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    state = _replay(lake, AS_OF)
    row = state.option_chain.iloc[0]
    assert row["delta"] == pytest.approx(0.51)
    assert row["gamma_method"] == "black76"
    assert row["gamma"] is not None


def test_oi_unconfirmed_warning(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    state = _replay(lake, AS_OF)
    assert "oi_semantics_unconfirmed" in state.warnings
    assert state.option_chain.iloc[0]["open_interest"] == 100.0


def test_index_latest_at_or_before(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    state = _replay(lake, AS_OF)
    assert state.index_state is not None
    assert state.index_state.price == pytest.approx(6001.0)
    assert state.index_state.index_source_dataset == "index_price_tick"


def test_no_lookahead_adversarial(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path, adversarial=True)
    state = _replay(lake, AS_OF)
    row = state.option_chain.iloc[0]
    assert row["latest_bid"] != 999.0
    assert row["last_trade_price"] != 9.99
    assert row["delta"] != 0.99
    assert row["open_interest"] != 99999
    assert state.index_state is not None
    assert state.index_state.price != 9999.0


def test_future_events_do_not_leak(tmp_path: Path) -> None:
    clean = _build_fixture_lake(tmp_path / "clean")
    adv = _build_fixture_lake(tmp_path / "adv", adversarial=True)
    s1 = _replay(clean, AS_OF)
    s2 = _replay(adv, AS_OF)
    r1 = s1.option_chain.iloc[0]
    r2 = s2.option_chain.iloc[0]
    assert r1["latest_bid"] == r2["latest_bid"]
    assert r1["last_trade_price"] == r2["last_trade_price"]
    assert r1["delta"] == r2["delta"]


def test_deterministic_state_hash(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    a = _replay(lake, AS_OF)
    b = _replay(lake, AS_OF)
    assert a.state_hash == b.state_hash
    assert len(a.state_hash) == 64


def test_manifest_created_at_not_in_state_hash(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    part = partition_dir(lake, "index_price_tick", TRADE, symbol="SPX")
    manifest = json.loads(manifest_path(part).read_text(encoding="utf-8"))
    manifest["created_at"] = "2099-01-01T00:00:00+00:00"
    manifest_path(part).write_text(json.dumps(manifest), encoding="utf-8")
    state = _replay(lake, AS_OF, strict_manifests=False)
    assert state.state_hash


def test_row_order_invariant_selection(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    part = partition_dir(lake, "option_quote_tick", TRADE, root=ROOT, expiration=TRADE)
    df = pd.read_parquet(part / "part-000.parquet")
    df_shuffled = df.sample(frac=1.0, random_state=0)
    df_shuffled.to_parquet(part / "part-000.parquet", index=False)
    from quant_lab.data.intraday_manifest import sha256_file

    manifest = json.loads(manifest_path(part).read_text(encoding="utf-8"))
    manifest["row_count"] = len(df_shuffled)
    manifest["files"][0]["sha256"] = sha256_file(part / "part-000.parquet")
    manifest["files"][0]["size_bytes"] = (part / "part-000.parquet").stat().st_size
    manifest_path(part).write_text(json.dumps(manifest), encoding="utf-8")
    s1 = _replay(lake, AS_OF)
    s2 = _replay(lake, AS_OF)
    assert s1.option_chain.iloc[0]["latest_bid"] == s2.option_chain.iloc[0]["latest_bid"]


def test_strict_missing_manifest_raises(tmp_path: Path) -> None:
    part = partition_dir(tmp_path, "index_price_1s", TRADE, symbol="SPX")
    part.mkdir(parents=True)
    with pytest.raises(MissingManifestError):
        _replay(tmp_path, strict_manifests=True)


def test_non_strict_degraded(tmp_path: Path) -> None:
    state = _replay(tmp_path, strict_manifests=False)
    assert any("missing_partition" in w for w in state.warnings)


def test_session_pre_market_and_post_close(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    pre = _replay(lake, session_datetime(TRADE, "09:00:00"))
    assert pre.session.phase == "pre_market"
    assert any("session_outside_rth" in w for w in pre.warnings)
    post = _replay(lake, session_datetime(TRADE, "16:30:00"))
    assert post.session.phase == "post_close"


def test_early_close_session(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    sess = build_session_metadata_row(
        trade_date=TRADE, root=ROOT, symbol="SPX", strike_range=2,
        window_start="09:30:00", window_end="13:00:00",
        quote_interval="tick", pilot_label="early",
    )
    sess.loc[sess.index[0], "session_rth_end"] = "13:00:00"
    ingest_partition(
        sess, lake_root=lake, dataset="session_metadata", trade_date=TRADE,
        root=ROOT, overwrite=True,
    )
    state = _replay(lake, session_datetime(TRADE, "12:00:00"))
    assert state.session.phase == "early_close"


def test_quote_fallback_to_1s(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    empty = normalize_option_quote(
        pd.DataFrame(columns=["timestamp", "expiration", "strike", "right", "bid", "ask"]),
        dataset="option_quote_tick", root=ROOT, trade_date=TRADE,
        source_endpoint="x", source_request_id="x",
    )
    ingest_partition(
        empty, lake_root=lake, dataset="option_quote_tick", trade_date=TRADE,
        root=ROOT, expiration=TRADE, overwrite=True,
    )
    state = _replay(lake, AS_OF)
    row = state.option_chain.iloc[0]
    assert row["quote_source_dataset"] == "option_quote_1s"
    assert "quote_fallback_1s" in row["data_quality_flags"]


def test_stale_quote_flag(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    state = _replay(lake, AS_OF, max_quote_age_seconds=5)
    assert "stale_quote" in state.option_chain.iloc[0]["data_quality_flags"]


def test_gex_adapter_shape(tmp_path: Path) -> None:
    lake = _build_fixture_lake(tmp_path)
    state = _replay(lake, AS_OF)
    adapted = to_gex_adapter_frame(state.option_chain)
    assert set(adapted.columns) >= {"strike", "right", "open_interest", "gamma"}


def test_pilot_replay_if_artifacts_exist() -> None:
    if not PILOT_LAKE_ROOT.is_dir():
        pytest.skip("pilot lake absent")
    state = replay_state(
        TRADE,
        session_datetime(TRADE, "13:01:00"),
        data_root=default_pilot_data_root(),
        strict_manifests=True,
    )
    assert len(state.option_chain) > 0
    assert state.index_state is not None
    assert state.state_hash


def test_compute_state_hash_stable_fields() -> None:
    req = ReplayRequest(trade_date=TRADE, as_of_timestamp=AS_OF, data_root=Path("x"))
    h = compute_state_hash(
        request=req,
        partitions=[],
        as_of=AS_OF,
        option_chain=pd.DataFrame(),
        index_state=None,
        warnings=["a"],
    )
    assert len(h) == 64
