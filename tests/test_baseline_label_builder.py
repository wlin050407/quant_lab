"""Tests for ML-P7.8.2 additive baseline primary-pin label builder."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_lab.data.intraday_time import SESSION_CLOSE, session_datetime
from quant_lab.ml.labels import (
    compute_all_labels,
    compute_baseline_p1_near,
    compute_baseline_p2_directional,
    compute_baseline_primary_pin_labels,
    compute_close_distance_to_primary_pin_em,
    evaluate_baseline_target_eligibility,
)
from quant_lab.ml.schemas import BASELINE_LABEL_SCHEMA_VERSION, AsOfContext, OutcomeContext

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


def _outcome(
    close: float,
    *,
    close_ts: object = CLOSE,
    path: pd.DataFrame | None = None,
) -> OutcomeContext:
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
        official_close_timestamp=close_ts,  # type: ignore[arg-type]
        official_close_source="test",
        session_close_timestamp=CLOSE,
        future_index_path=path,
    )


def test_p0_points_formula() -> None:
    baseline = compute_baseline_primary_pin_labels(
        official_close=5010.0,
        primary_pin_t=5000.0,
        remaining_expected_move_t=20.0,
        as_of_timestamp=AS_OF,
        label_source_timestamp=CLOSE,
    )
    assert baseline.close_distance_to_primary_pin_points == pytest.approx(10.0)


def test_p0_em_formula() -> None:
    d_em = compute_close_distance_to_primary_pin_em(5010.0, 5000.0, 20.0)
    assert d_em == pytest.approx(0.5)
    baseline = compute_baseline_primary_pin_labels(
        official_close=5010.0,
        primary_pin_t=5000.0,
        remaining_expected_move_t=20.0,
        as_of_timestamp=AS_OF,
        label_source_timestamp=CLOSE,
    )
    assert baseline.close_distance_to_primary_pin_em == pytest.approx(0.5)


def test_sign_convention_positive_negative() -> None:
    above = compute_baseline_primary_pin_labels(
        official_close=5010.0,
        primary_pin_t=5000.0,
        remaining_expected_move_t=20.0,
        as_of_timestamp=AS_OF,
        label_source_timestamp=CLOSE,
    )
    below = compute_baseline_primary_pin_labels(
        official_close=4990.0,
        primary_pin_t=5000.0,
        remaining_expected_move_t=20.0,
        as_of_timestamp=AS_OF,
        label_source_timestamp=CLOSE,
    )
    assert above.close_distance_to_primary_pin_em is not None
    assert above.close_distance_to_primary_pin_em > 0
    assert below.close_distance_to_primary_pin_em is not None
    assert below.close_distance_to_primary_pin_em < 0


def test_missing_primary_pin_exclusion() -> None:
    baseline = compute_baseline_primary_pin_labels(
        official_close=5010.0,
        primary_pin_t=None,
        remaining_expected_move_t=20.0,
        as_of_timestamp=AS_OF,
        label_source_timestamp=CLOSE,
    )
    assert baseline.baseline_target_eligible is False
    assert "missing_primary_pin" in baseline.baseline_target_exclusion_reasons
    assert baseline.close_distance_to_primary_pin_em is None


def test_remaining_em_non_positive_exclusion() -> None:
    baseline = compute_baseline_primary_pin_labels(
        official_close=5010.0,
        primary_pin_t=5000.0,
        remaining_expected_move_t=0.0,
        as_of_timestamp=AS_OF,
        label_source_timestamp=CLOSE,
    )
    assert baseline.baseline_target_eligible is False
    assert "remaining_em_invalid" in baseline.baseline_target_exclusion_reasons


def test_remaining_em_nan_exclusion() -> None:
    baseline = compute_baseline_primary_pin_labels(
        official_close=5010.0,
        primary_pin_t=5000.0,
        remaining_expected_move_t=float("nan"),
        as_of_timestamp=AS_OF,
        label_source_timestamp=CLOSE,
    )
    assert baseline.baseline_target_eligible is False
    assert "remaining_em_invalid" in baseline.baseline_target_exclusion_reasons


def test_missing_official_close_exclusion() -> None:
    ok, reasons = evaluate_baseline_target_eligibility(
        primary_pin_t=5000.0,
        remaining_expected_move_t=20.0,
        official_close=None,
        label_source_timestamp=CLOSE,
        as_of_timestamp=AS_OF,
    )
    assert ok is False
    assert "missing_official_close" in reasons


def test_label_source_not_after_as_of_exclusion() -> None:
    baseline = compute_baseline_primary_pin_labels(
        official_close=5010.0,
        primary_pin_t=5000.0,
        remaining_expected_move_t=20.0,
        as_of_timestamp=AS_OF,
        label_source_timestamp=AS_OF,
    )
    assert baseline.baseline_target_eligible is False
    assert "label_source_not_after_as_of" in baseline.baseline_target_exclusion_reasons


def test_p1_025_near_true_false() -> None:
    assert compute_baseline_p1_near(0.1, 0.25) is True
    assert compute_baseline_p1_near(0.4, 0.25) is False


def test_p1_050_near_true_false() -> None:
    assert compute_baseline_p1_near(0.1, 0.50) is True
    assert compute_baseline_p1_near(0.4, 0.50) is True
    assert compute_baseline_p1_near(0.6, 0.50) is False


def test_p2_025_below_near_above() -> None:
    assert compute_baseline_p2_directional(-0.5, 0.25) == "below"
    assert compute_baseline_p2_directional(0.1, 0.25) == "near"
    assert compute_baseline_p2_directional(0.5, 0.25) == "above"


def test_p2_050_below_near_above() -> None:
    assert compute_baseline_p2_directional(-0.6, 0.50) == "below"
    assert compute_baseline_p2_directional(0.2, 0.50) == "near"
    assert compute_baseline_p2_directional(0.6, 0.50) == "above"


def test_baseline_target_eligible_true_case() -> None:
    baseline = compute_baseline_primary_pin_labels(
        official_close=5010.0,
        primary_pin_t=5000.0,
        remaining_expected_move_t=20.0,
        as_of_timestamp=AS_OF,
        label_source_timestamp=CLOSE,
    )
    assert baseline.baseline_target_eligible is True
    assert baseline.baseline_target_exclusion_reasons == ()
    assert baseline.close_near_primary_pin_025 is False
    assert baseline.close_near_primary_pin_050 is True


def test_baseline_label_schema_version() -> None:
    baseline = compute_baseline_primary_pin_labels(
        official_close=5010.0,
        primary_pin_t=5000.0,
        remaining_expected_move_t=20.0,
        as_of_timestamp=AS_OF,
        label_source_timestamp=CLOSE,
    )
    assert baseline.baseline_label_schema_version == BASELINE_LABEL_SCHEMA_VERSION


def test_existing_zone_labels_unchanged_with_baseline() -> None:
    ctx = _ctx()
    outcome = _outcome(6001.0)
    row = compute_all_labels(ctx, outcome)
    assert row.close_location_vs_current_zone == "inside"
    assert row.close_inside_current_zone is True
    assert row.baseline_target_eligible is True
    assert row.baseline_label_schema_version == BASELINE_LABEL_SCHEMA_VERSION
    assert row.close_near_primary_pin_050 is not None


def test_zone_labels_unchanged_when_no_zone() -> None:
    ctx = _ctx(has_valid_zone=False, zone_low_t=None, zone_high_t=None)
    row = compute_all_labels(ctx, _outcome(6001.0))
    assert row.close_location_vs_current_zone is None
    assert "no_valid_zone_at_as_of" in row.exclusion_reasons
    assert row.baseline_target_eligible is True


def test_baseline_null_when_leakage_guard_fails_in_compute_all_labels() -> None:
    row = compute_all_labels(_ctx(), _outcome(6010.0, close_ts=AS_OF))
    assert row.baseline_target_eligible is False
    assert row.close_distance_to_primary_pin_em is None
    assert "label_source_not_after_as_of" in row.baseline_target_exclusion_reasons


def test_v1_row_dict_includes_baseline_fields() -> None:
    from quant_lab.ml.schemas import LABEL_SCHEMA_VERSION, DatasetRow

    row = compute_all_labels(_ctx(), _outcome(6001.0))
    dataset_row = DatasetRow(context=_ctx(), labels=row, anchor_type="regular_5min")
    d = dataset_row.row_dict()
    assert d["label_schema_version"] == LABEL_SCHEMA_VERSION
    assert d["labels.baseline_label_schema_version"] == BASELINE_LABEL_SCHEMA_VERSION
    assert d["labels.baseline_target_eligible"] is True
    assert "labels.close_near_primary_pin_025" in d
    assert "labels.close_near_primary_pin_050" in d


def test_exit_labels_unchanged() -> None:
    path = pd.DataFrame(
        {
            "event_timestamp": [
                session_datetime(TRADE, "13:05:00"),
                session_datetime(TRADE, "13:10:00"),
            ],
            "price": [6001.0, 6003.0],
        }
    )
    row = compute_all_labels(_ctx(), _outcome(6001.0, path=path))
    assert row.first_zone_exit_direction == "up"
    assert row.valid_upside_exit_15m is not None
