"""Tests for strict feature+label join."""

from __future__ import annotations

import pytest

from quant_lab.ml.datasets.join import (
    JoinKeyMismatchError,
    extract_join_keys,
    strict_join_batches,
    strict_join_label_feature,
)


def _label_row(**overrides: object) -> dict:
    base = {
        "trade_date": "2024-01-05",
        "as_of_timestamp": "2024-01-05T13:01:00-05:00",
        "replay_state_hash": "abc123",
        "deterministic_bundle_hash": "def456",
        "labels.close_location_vs_current_zone": "inside",
        "sample_weight": 1.0,
        "exclusion_reasons": [],
        "warning_codes": [],
    }
    base.update(overrides)
    return base


def _feature_row(**overrides: object) -> dict:
    base = {
        "trade_date": "2024-01-05",
        "as_of_timestamp": "2024-01-05T13:01:00-05:00",
        "replay_state_hash": "abc123",
        "deterministic_bundle_hash": "def456",
        "features.spot_t": 6000.0,
    }
    base.update(overrides)
    return base


def test_strict_join_success() -> None:
    joined = strict_join_label_feature(_label_row(), _feature_row())
    d = joined.to_dict()
    assert d["labels.close_location_vs_current_zone"] == "inside"
    assert d["features.spot_t"] == 6000.0
    assert d["join_keys_verified"] is True


def test_join_key_mismatch_rejected() -> None:
    with pytest.raises(JoinKeyMismatchError):
        strict_join_label_feature(_label_row(), _feature_row(replay_state_hash="other"))


def test_batch_join_by_hash_index() -> None:
    labels = [_label_row(), _label_row(as_of_timestamp="2024-01-05T13:06:00-05:00", replay_state_hash="x2")]
    features = [
        _feature_row(as_of_timestamp="2024-01-05T13:06:00-05:00", replay_state_hash="x2"),
        _feature_row(),
    ]
    joined = strict_join_batches(labels, features)
    assert len(joined) == 2


def test_extract_join_keys_required() -> None:
    with pytest.raises(JoinKeyMismatchError):
        extract_join_keys({"trade_date": "2024-01-05"})
