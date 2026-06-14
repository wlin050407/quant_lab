"""Tests for ML-P6 leakage checks."""

from __future__ import annotations

from datetime import date

from quant_lab.data.intraday_time import session_datetime
from quant_lab.ml.leakage import (
    LeakageViolationType,
    assert_adversarial_injection_rejected,
    check_feature_timestamp_cutoff,
    check_future_market_data_in_features,
    check_label_separate_from_features,
    check_label_timestamp_after_as_of,
    check_no_final_volume_in_features,
    check_post_close_zone_recompute,
    check_split_config,
    check_zone_for_label_matches_as_of,
    validate_dataset_rows_no_feature_leakage,
)
from quant_lab.ml.schemas import AsOfContext

TRADE = date(2026, 6, 10)
AS_OF = session_datetime(TRADE, "13:00:00")
CLOSE = session_datetime(TRADE, "16:00:00")


def _ctx(zone_low: float = 6000.0, zone_high: float = 6002.0) -> AsOfContext:
    return AsOfContext(
        trade_date=TRADE,
        as_of_timestamp=AS_OF,
        spot_t=6001.0,
        primary_pin_t=6000.0,
        secondary_pin_t=6002.0,
        zone_low_t=zone_low,
        zone_high_t=zone_high,
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


def test_future_quote_rejected() -> None:
    future = session_datetime(TRADE, "13:05:00")
    result = check_future_market_data_in_features(AS_OF, quote_ts=future)
    assert not result.passed
    assert LeakageViolationType.FUTURE_QUOTE_IN_FEATURES in {v.violation_type for v in result.violations}


def test_future_trade_rejected() -> None:
    result = check_future_market_data_in_features(AS_OF, trade_ts=session_datetime(TRADE, "14:00:00"))
    assert not result.passed


def test_future_greek_rejected() -> None:
    result = check_future_market_data_in_features(AS_OF, greek_ts=session_datetime(TRADE, "14:00:00"))
    assert not result.passed


def test_future_gamma_rejected() -> None:
    result = check_future_market_data_in_features(AS_OF, gamma_ts=session_datetime(TRADE, "14:00:00"))
    assert not result.passed


def test_future_index_rejected() -> None:
    result = check_future_market_data_in_features(AS_OF, index_ts=session_datetime(TRADE, "14:00:00"))
    assert not result.passed


def test_next_day_oi_rejected() -> None:
    result = check_future_market_data_in_features(
        AS_OF,
        oi_trade_date="2026-06-11",
        feature_trade_date="2026-06-10",
    )
    assert not result.passed


def test_final_volume_feature_rejected() -> None:
    result = check_no_final_volume_in_features(["spot_t", "final_volume"])
    assert not result.passed


def test_post_close_zone_recompute_rejected() -> None:
    result = check_post_close_zone_recompute(session_datetime(TRADE, "16:05:00"), CLOSE)
    assert not result.passed


def test_random_row_split_rejected() -> None:
    result = check_split_config(shuffle=True)
    assert not result.passed
    result2 = check_split_config(split_method="random_row")
    assert not result2.passed


def test_label_timestamp_must_be_after_as_of() -> None:
    result = check_label_timestamp_after_as_of(AS_OF, AS_OF)
    assert not result.passed


def test_zone_mismatch_rejected() -> None:
    result = check_zone_for_label_matches_as_of(5990.0, 5995.0, _ctx())
    assert not result.passed


def test_label_separate_from_features() -> None:
    result = check_label_separate_from_features({"spot_t": 1.0, "labels.close_inside_current_zone": True})
    assert not result.passed


def test_feature_cutoff_adversarial() -> None:
    assert_adversarial_injection_rejected(
        LeakageViolationType.FEATURE_AFTER_AS_OF,
        lambda: check_feature_timestamp_cutoff(
            AS_OF,
            [("quote", session_datetime(TRADE, "13:30:00"))],
        ),
    )


def test_dataset_rows_labels_separate() -> None:
    rows = [{"as_of_timestamp": AS_OF.isoformat(), "feature_cutoff_timestamp": AS_OF.isoformat(), "spot_t": 1.0}]
    assert validate_dataset_rows_no_feature_leakage(rows).passed
