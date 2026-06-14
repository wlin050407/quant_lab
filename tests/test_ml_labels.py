"""Tests for ML-P6 label functions."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_lab.data.intraday_time import SESSION_CLOSE, session_datetime
from quant_lab.ml.labels import (
    DEFAULT_PIN_TOLERANCE_CONFIGS,
    PinToleranceConfig,
    compute_all_labels,
    compute_close_inside_zone,
    compute_close_location_vs_zone,
    compute_exit_labels,
    compute_forward_realized_vol,
    compute_near_pin,
    compute_normalized_close_move,
    remaining_expected_move,
)
from quant_lab.ml.schemas import AsOfContext, OutcomeContext

TRADE = date(2026, 6, 10)
AS_OF = session_datetime(TRADE, "13:00:00")
CLOSE = session_datetime(TRADE, SESSION_CLOSE)


def _ctx(**kwargs: object) -> AsOfContext:
    defaults = dict(
        trade_date=TRADE,
        as_of_timestamp=AS_OF,
        spot_t=6000.0,
        primary_pin_t=6000.0,
        secondary_pin_t=6002.0,
        zone_low_t=6000.0,
        zone_high_t=6002.0,
        zone_center_t=6001.0,
        zone_break_up=6005.0,
        zone_break_down=5997.0,
        pin_score_t=0.5,
        expected_move_t=40.0,
        gamma_source="derived_black76_precomputed",
        oi_semantics_status="unconfirmed",
        spot_zone_state_at_as_of="inside_zone",
        has_valid_zone=True,
        quality_score=0.9,
        replay_state_hash="abc",
        deterministic_bundle_hash="def",
        source_partition_hashes=(),
    )
    defaults.update(kwargs)
    return AsOfContext(**defaults)


def _outcome(close: float, path: pd.DataFrame | None = None) -> OutcomeContext:
    if path is None:
        path = pd.DataFrame(
            {
                "event_timestamp": [
                    session_datetime(TRADE, "13:05:00"),
                    session_datetime(TRADE, "15:55:00"),
                    CLOSE,
                ],
                "price": [6003.0, close, close],
            }
        )
    return OutcomeContext(
        official_close=close,
        official_close_timestamp=CLOSE,
        official_close_source="test",
        session_close_timestamp=CLOSE,
        future_index_path=path,
    )


def test_close_location_below_inside_above() -> None:
    assert compute_close_location_vs_zone(5999.0, 6000.0, 6002.0) == "below"
    assert compute_close_location_vs_zone(6001.0, 6000.0, 6002.0) == "inside"
    assert compute_close_location_vs_zone(6003.0, 6000.0, 6002.0) == "above"


def test_close_location_boundary_inclusive() -> None:
    assert compute_close_location_vs_zone(6000.0, 6000.0, 6002.0) == "inside"
    assert compute_close_location_vs_zone(6002.0, 6000.0, 6002.0) == "inside"


def test_close_location_no_zone() -> None:
    assert compute_close_location_vs_zone(6001.0, None, None) is None


def test_close_inside_zone() -> None:
    assert compute_close_inside_zone(6001.0, 6000.0, 6002.0) is True
    assert compute_close_inside_zone(5999.0, 6000.0, 6002.0) is False


def test_normalized_close_move() -> None:
    rem = remaining_expected_move(40.0, AS_OF, CLOSE)
    assert rem is not None and rem > 0
    val, reason = compute_normalized_close_move(6010.0, 6000.0, rem)
    assert reason is None
    assert val == pytest.approx(10.0 / rem)


def test_normalized_close_move_missing_em() -> None:
    val, reason = compute_normalized_close_move(6010.0, 6000.0, None)
    assert val is None
    assert reason == "missing_or_invalid_remaining_expected_move"


def test_near_pin_tolerances() -> None:
    cfg = DEFAULT_PIN_TOLERANCE_CONFIGS["fixed_2.5pt"]
    assert compute_near_pin(6002.0, 6000.0, 6000.0, 20.0, cfg) is True
    assert compute_near_pin(6010.0, 6000.0, 6000.0, 20.0, cfg) is False


def test_exit_labels_zone_cross_up() -> None:
    path = pd.DataFrame(
        {
            "event_timestamp": [
                session_datetime(TRADE, "13:05:00"),
                session_datetime(TRADE, "13:10:00"),
            ],
            "price": [6001.0, 6003.0],
        }
    )
    labels = compute_exit_labels(_ctx(), path, AS_OF, CLOSE)
    assert labels["first_zone_exit_direction"] == "up"
    assert labels["exit_before_close"] is True


def test_exit_labels_already_outside_zone() -> None:
    path = pd.DataFrame({"event_timestamp": [session_datetime(TRADE, "13:05:00")], "price": [6010.0]})
    labels = compute_exit_labels(_ctx(spot_zone_state_at_as_of="above_break"), path, AS_OF, CLOSE)
    assert labels["_exclusion"] == "already_outside_zone_at_as_of"


def test_forward_realized_vol_horizon_insufficient() -> None:
    path = pd.DataFrame(
        {"event_timestamp": [session_datetime(TRADE, "13:01:00")], "price": [6000.0]}
    )
    vol = compute_forward_realized_vol(path, AS_OF, 15.0)
    assert vol is None


def test_compute_all_labels_no_zone() -> None:
    row = compute_all_labels(_ctx(has_valid_zone=False, zone_low_t=None, zone_high_t=None), _outcome(6001.0))
    assert row.close_location_vs_current_zone is None
    assert "no_valid_zone_at_as_of" in row.exclusion_reasons


def test_pin_tolerance_config_em_fraction() -> None:
    cfg = PinToleranceConfig(remaining_em_fraction=0.10)
    assert cfg.tolerance_points(6000.0, 20.0) == pytest.approx(2.0)
