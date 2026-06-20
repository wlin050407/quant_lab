"""Tests for ML-P8B.0 forbidden input validators."""

from __future__ import annotations

from quant_lab.ml.harness.validators import validate_forbidden_features


def test_forbidden_exact_columns_fail() -> None:
    cols = ["spot_t", "official_close", "quote_30s_mean_bid_ask_spread"]
    result = validate_forbidden_features(cols)
    assert result.passed is False
    assert "official_close" in result.forbidden_columns


def test_labels_prefix_forbidden() -> None:
    cols = ["labels.close_distance_to_primary_pin_em", "as_of_timestamp"]
    result = validate_forbidden_features(cols)
    assert result.passed is False
    assert any(c.startswith("labels.") for c in result.forbidden_columns)


def test_target_fields_forbidden_without_prefix() -> None:
    cols = ["close_near_primary_pin_050", "primary_pin_t"]
    result = validate_forbidden_features(cols)
    assert result.passed is False
    assert "close_near_primary_pin_050" in result.forbidden_columns


def test_allowlisted_metadata_passes() -> None:
    cols = [
        "as_of_timestamp",
        "trade_date",
        "replay_state_hash",
        "deterministic_bundle_hash",
        "spot_t",
        "quote_30s_mean_bid_ask_spread",
    ]
    result = validate_forbidden_features(cols)
    assert result.passed is True
    assert result.forbidden_columns == []


def test_future_fields_forbidden() -> None:
    cols = ["future_return", "index_30s_mean_return"]
    result = validate_forbidden_features(cols)
    assert result.passed is False
    assert "future_return" in result.forbidden_columns
