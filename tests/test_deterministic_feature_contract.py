"""ML-P5 deterministic feature contract tests (no network)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from quant_lab.data.point_in_time_replay import (
    DETERMINISTIC_INPUT_COLUMNS,
    compute_deterministic_bundle,
    deterministic_input_to_factor_chain,
    to_deterministic_input_frame,
)
from quant_lab.factors.gex import (
    compute_dealer_gamma_exposure,
    filter_chain_by_dte,
    total_net_gex,
)
from quant_lab.factors.pin_cluster import (
    CLUSTER_MAX_DIST_PCT,
    CLUSTER_MIN_STRENGTH_RATIO,
    compute_zone_break,
    detect_pin_cluster,
    spot_zone_state,
)
from quant_lab.factors.positioning import expected_move_1sd

SPOT = 6000.0
TRADE = date(2026, 6, 10)


def _synthetic_input(*, with_gamma: bool = True, oi_unconfirmed: bool = True) -> pd.DataFrame:
    strikes = [5950.0, 5975.0, 6000.0, 6025.0, 6050.0]
    rows: list[dict[str, object]] = []
    for strike in strikes:
        for right in ("CALL", "PUT"):
            rows.append(
                {
                    "strike": strike,
                    "right": right,
                    "open_interest": 500 + (strike - 5950),
                    "spot": SPOT,
                    "implied_vol": 0.15,
                    "gamma": 0.0001 * (6000 / strike) if with_gamma else None,
                    "gamma_method": "black76" if with_gamma else None,
                    "gamma_method_version": "1.0.0" if with_gamma else None,
                    "bid": 1.0,
                    "ask": 1.1,
                    "mid": 1.05,
                    "expiration": TRADE.isoformat(),
                    "time_to_expiry_years": 0.001,
                    "contract_identifier": f"SPXW|{TRADE}|{strike}|{right}",
                    "quote_timestamp": "2026-06-10T13:01:00-04:00",
                    "greek_timestamp": "2026-06-10T13:01:00-04:00",
                    "oi_event_timestamp": "2026-06-10T06:30:00-04:00",
                    "oi_semantics_status": "unconfirmed" if oi_unconfirmed else "confirmed",
                    "oi_publication_time_confirmed": not oi_unconfirmed,
                    "data_quality_flags": "oi_semantics_unconfirmed" if oi_unconfirmed else "",
                }
            )
    return pd.DataFrame(rows)[list(DETERMINISTIC_INPUT_COLUMNS)]


def test_deterministic_input_schema_frozen() -> None:
    df = _synthetic_input()
    assert list(df.columns) == list(DETERMINISTIC_INPUT_COLUMNS)
    assert (df["gamma_method"] == "black76").all()


def test_factor_chain_preserves_metadata() -> None:
    inp = _synthetic_input()
    chain = deterministic_input_to_factor_chain(inp, spot=SPOT)
    assert chain["right"].isin(["C", "P"]).all()
    assert (chain["gamma_method"] == "black76").all()
    assert (chain["oi_semantics_status"] == "unconfirmed").all()


def test_missing_gamma_excluded_not_zero() -> None:
    inp = _synthetic_input(with_gamma=False)
    chain = deterministic_input_to_factor_chain(inp, spot=SPOT)
    cohort = filter_chain_by_dte(chain, dte_max=1)
    per = compute_dealer_gamma_exposure(cohort, SPOT, gamma_col="bs_gamma")
    assert per.empty or total_net_gex(per) == 0.0


def test_gex_deterministic_same_input() -> None:
    inp = _synthetic_input()
    a = compute_deterministic_bundle(inp, SPOT, use_precomputed_gamma=True)
    b = compute_deterministic_bundle(inp, SPOT, use_precomputed_gamma=True)
    assert a.net_gex == b.net_gex
    assert a.king_node == b.king_node
    assert a.gamma_source == "derived_black76_precomputed"


def test_oi_unconfirmed_metadata_preserved() -> None:
    bundle = compute_deterministic_bundle(_synthetic_input(), SPOT)
    assert bundle.oi_semantics_status == "unconfirmed"
    assert "oi_semantics_unconfirmed" in bundle.data_quality_flags


def test_recomputed_path_matches_terminal_row() -> None:
    from quant_lab.terminal.snapshot import _row_from_chain

    inp = _synthetic_input()
    chain = deterministic_input_to_factor_chain(inp, spot=SPOT, dte=0)
    chain["dte"] = 0
    row = _row_from_chain(chain, SPOT, asof=TRADE, hours_to_close=3.0)
    bundle = compute_deterministic_bundle(
        inp, SPOT, asof=TRADE, hours_to_close=3.0, use_precomputed_gamma=False
    )
    assert bundle.net_gex == pytest.approx(row["net_gex_dte1"], rel=1e-6)
    assert bundle.king_node == pytest.approx(row["king_dte1"], rel=1e-6)
    if np.isfinite(row["flip_dte1"]):
        assert bundle.flip_level == pytest.approx(row["flip_dte1"], rel=1e-6)
    else:
        assert not np.isfinite(bundle.flip_level)


def test_adapter_roundtrip_from_replay_shape() -> None:
    replay = pd.DataFrame(
        {
            "strike": [6000.0],
            "right": ["CALL"],
            "open_interest": [100.0],
            "underlying_price_from_greeks": [6000.0],
            "implied_vol": [0.15],
            "gamma": [0.0001],
            "gamma_method": ["black76"],
            "gamma_method_version": ["1.0.0"],
            "latest_bid": [1.0],
            "latest_ask": [1.1],
            "expiration": [TRADE.isoformat()],
            "contract_identifier": ["SPXW|2026-06-10|6000.0|CALL"],
            "latest_quote_timestamp": ["2026-06-10T13:01:00-04:00"],
            "greek_timestamp": ["2026-06-10T13:01:00-04:00"],
            "oi_event_timestamp": ["2026-06-10T06:30:00-04:00"],
            "oi_semantics_status": ["unconfirmed"],
            "oi_publication_time_confirmed": [False],
            "data_quality_flags": [""],
        }
    )
    frozen = to_deterministic_input_frame(replay, spot=SPOT)
    assert frozen["gamma_method"].iloc[0] == "black76"
    assert frozen["oi_semantics_status"].iloc[0] == "unconfirmed"


def test_pin_zone_distance_threshold_below() -> None:
    spot = 6000.0
    dist = spot * CLUSTER_MAX_DIST_PCT * 0.99
    rows = [
        {"strike": 6000.0, "weight_pct": 50.0},
        {"strike": 6000.0 + dist, "weight_pct": 49.0},
    ]
    assert detect_pin_cluster(rows, spot, regime="long_gamma", pin_reliability="high").is_cluster


def test_pin_zone_distance_threshold_above() -> None:
    spot = 6000.0
    dist = spot * CLUSTER_MAX_DIST_PCT * 1.01
    rows = [
        {"strike": 6000.0, "weight_pct": 50.0},
        {"strike": 6000.0 + dist, "weight_pct": 49.0},
    ]
    result = detect_pin_cluster(rows, spot, regime="long_gamma", pin_reliability="high")
    assert result.is_cluster is False
    assert result.merge_reason == "strikes_too_far_apart"


def test_pin_zone_strength_threshold_below() -> None:
    rows = [{"strike": 6000.0, "weight_pct": 80.0}, {"strike": 6010.0, "weight_pct": 55.0}]
    result = detect_pin_cluster(rows, 6000.0, regime="long_gamma", pin_reliability="high")
    assert result.is_cluster is False
    assert result.merge_reason == "secondary_too_weak"


def test_pin_zone_strength_threshold_above() -> None:
    ratio = CLUSTER_MIN_STRENGTH_RATIO + 0.01
    rows = [{"strike": 6000.0, "weight_pct": 100.0}, {"strike": 6010.0, "weight_pct": 100.0 * ratio}]
    result = detect_pin_cluster(rows, 6000.0, regime="long_gamma", pin_reliability="high")
    assert result.is_cluster is True


def test_valid_exit_buffer_and_states() -> None:
    spot = 6000.0
    lo, hi = 5990.0, 6010.0
    zb = compute_zone_break(lo, hi, symbol="SPX", spot=spot)
    assert zb.buffer_pts == pytest.approx(max(5.0, 0.25 * (hi - lo)))
    assert spot_zone_state(spot, zone_low=lo, zone_high=hi, zone_break=zb) == "inside_zone"
    assert spot_zone_state(hi + 1.0, zone_low=lo, zone_high=hi, zone_break=zb) == "testing_upside_exit"
    assert spot_zone_state(zb.up_break_level + 1.0, zone_low=lo, zone_high=hi, zone_break=zb) == "above_break"
    assert spot_zone_state(lo - 1.0, zone_low=lo, zone_high=hi, zone_break=zb) == "testing_downside_exit"
    assert spot_zone_state(zb.down_break_level - 1.0, zone_low=lo, zone_high=hi, zone_break=zb) == "below_break"


def test_expected_move_contract() -> None:
    em = expected_move_1sd(6000.0, 0.20, time_years=1.0 / 365.0)
    assert em == pytest.approx(6000.0 * 0.20 * np.sqrt(1.0 / 365.0))
    assert np.isnan(expected_move_1sd(6000.0, float("nan")))


def test_zero_oi_and_only_calls() -> None:
    inp = _synthetic_input()
    inp.loc[inp["right"] == "PUT", "open_interest"] = 0.0
    bundle = compute_deterministic_bundle(inp, SPOT)
    assert np.isfinite(bundle.net_gex)


def test_terminal_helper_does_not_mutate_chain() -> None:
    from quant_lab.terminal.snapshot import _row_from_chain

    inp = _synthetic_input()
    chain = deterministic_input_to_factor_chain(inp, spot=SPOT)
    before = chain.copy()
    _row_from_chain(chain, SPOT, asof=TRADE)
    pd.testing.assert_frame_equal(chain, before)
