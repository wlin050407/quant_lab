"""Tests for ML-P7 feature leakage checks."""

from __future__ import annotations

from datetime import date

from quant_lab.data.intraday_time import session_datetime
from quant_lab.ml.features.leakage import (
    check_adversarial_feature_injection,
    check_feature_row_leakage,
    check_no_label_columns_in_features,
)

TRADE = date(2026, 6, 10)
AS_OF = session_datetime(TRADE, "13:00:00")


def test_labels_cannot_enter_features() -> None:
    result = check_no_label_columns_in_features({"labels.close_inside_current_zone": True})
    assert not result.passed


def test_official_close_rejected() -> None:
    result = check_no_label_columns_in_features({"official_close": 6000.0})
    assert not result.passed


def test_future_path_rejected() -> None:
    result = check_no_label_columns_in_features({"future_index_path": []})
    assert not result.passed


def test_final_volume_rejected() -> None:
    result = check_no_label_columns_in_features({"final_volume": 1000})
    assert not result.passed


def test_feature_source_timestamp_violation() -> None:
    future = session_datetime(TRADE, "14:00:00")
    row = {
        "as_of_timestamp": AS_OF.isoformat(),
        "features.spot_t": 6000.0,
    }
    result = check_feature_row_leakage(row, AS_OF, source_timestamp_max=future)
    assert not result.passed


def test_adversarial_future_quote() -> None:
    result = check_adversarial_feature_injection(
        AS_OF,
        quote_ts=session_datetime(TRADE, "13:30:00"),
    )
    assert not result.passed


def test_adversarial_label_in_feature_dict() -> None:
    result = check_adversarial_feature_injection(
        AS_OF,
        feature_dict={"normalized_close_move": 0.5},
    )
    assert not result.passed


def test_join_key_mismatch_detected() -> None:
    row = {"features.spot_t": 1.0}
    result = check_feature_row_leakage(
        row,
        AS_OF,
        source_timestamp_max=AS_OF,
        join_keys={"replay_state_hash": "a"},
        label_row_keys={"replay_state_hash": "b"},
    )
    assert not result.passed
