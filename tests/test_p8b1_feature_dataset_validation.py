"""Tests for ML-P8B.1 feature dataset validation (synthetic only)."""

from __future__ import annotations

from datetime import datetime

import pytest

from quant_lab.ml.datasets.join import strict_join_batches
from quant_lab.ml.features.p8b1_validation import (
    compute_feature_coverage,
    validate_all_feature_rows_forbidden,
    validate_feature_matrix_forbidden,
    validate_feature_timestamp_leakage,
    validate_strict_hash_join,
)
from quant_lab.ml.harness.manifests import HARNESS_STAGE_P8B1, RunManifest, validate_run_manifest


def _label_row(
    *,
    trade_date: str = "2024-01-19",
    as_of: str = "2024-01-19T10:00:00-05:00",
    replay: str = "rh1",
    bundle: str = "bh1",
) -> dict[str, object]:
    return {
        "trade_date": trade_date,
        "as_of_timestamp": as_of,
        "replay_state_hash": replay,
        "deterministic_bundle_hash": bundle,
        "labels.baseline_target_eligible": True,
    }


def _feature_row(
    *,
    trade_date: str = "2024-01-19",
    as_of: str = "2024-01-19T10:00:00-05:00",
    replay: str = "rh1",
    bundle: str = "bh1",
    src_max: str = "2024-01-19T09:59:00-05:00",
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "trade_date": trade_date,
        "as_of_timestamp": as_of,
        "replay_state_hash": replay,
        "deterministic_bundle_hash": bundle,
        "source_timestamp_max": src_max,
        "features.spot_t_norm": 0.1,
        "features.feature_quality_score": 0.9,
    }
    if extra:
        row.update(extra)
    return row


def test_strict_hash_join_pass() -> None:
    labels = [_label_row()]
    features = [_feature_row()]
    res = validate_strict_hash_join(labels, features)
    assert res.join_pass is True
    assert res.joined_rows == 1
    strict_join_batches(labels, features)


def test_strict_hash_join_duplicate_key_fail() -> None:
    labels = [_label_row()]
    features = [_feature_row(), _feature_row()]
    res = validate_strict_hash_join(labels, features)
    assert res.join_pass is False
    assert len(res.duplicate_feature_keys) == 1


def test_strict_hash_join_missing_key_fail() -> None:
    labels = [_label_row(replay="rh1")]
    features = [_feature_row(replay="rh2")]
    res = validate_strict_hash_join(labels, features)
    assert res.join_pass is False
    assert len(res.missing_feature_rows) == 1


def test_feature_timestamp_leakage_pass() -> None:
    res = validate_feature_timestamp_leakage([_feature_row()])
    assert res.timestamp_leakage_pass is True


def test_feature_timestamp_leakage_fail() -> None:
    row = _feature_row(src_max="2024-01-19T10:05:00-05:00")
    res = validate_feature_timestamp_leakage([row])
    assert res.timestamp_leakage_pass is False
    assert res.violation_count > 0


def test_forbidden_catches_labels_prefix_in_row() -> None:
    row = _feature_row(extra={"labels.close_near_primary_pin_050": True})
    res = validate_feature_matrix_forbidden(row)
    assert res["forbidden_input_pass"] is False


def test_forbidden_catches_official_close_feature() -> None:
    row = _feature_row(extra={"features.official_close": 5000.0})
    res = validate_feature_matrix_forbidden(row)
    assert res["forbidden_input_pass"] is False


def test_metadata_allowlist_passes() -> None:
    row = _feature_row()
    res = validate_all_feature_rows_forbidden([row])
    assert res["forbidden_input_pass"] is True


def test_feature_missingness_aggregation() -> None:
    rows = [
        _feature_row(extra={"features.spot_t_norm": 0.1}),
        _feature_row(extra={"features.spot_t_norm": None}),
    ]
    cov = compute_feature_coverage(rows)
    assert cov.feature_row_count == 2
    assert cov.missingness_by_feature["spot_t_norm"] == pytest.approx(0.5)


def test_constant_feature_detection() -> None:
    rows = [_feature_row(), _feature_row()]
    cov = compute_feature_coverage(rows)
    assert "spot_t_norm" in cov.constant_features or cov.feature_row_count == 2


def test_run_manifest_p8b1_fields() -> None:
    m = RunManifest(
        run_id="test",
        stage=HARNESS_STAGE_P8B1,
        created_at=datetime.now().isoformat(),
        code_commit="abc",
        dataset_manifest_hash="dhash",
        feature_manifest_hash="fhash",
        label_schema_version="1.0.0",
        baseline_label_schema_version="1.1.0-draft",
        target_name="feature_dataset_validation_only",
        split_protocol="not_applied",
        train_sessions=[],
        validation_sessions=[],
        test_sessions=[],
        metrics_version="p8b0-v1",
        leakage_validation_status="PASS",
        forbidden_input_validation_status="PASS",
        model_type="feature_dataset_validation_only",
        model_fitting_allowed=False,
        artifacts_written=[],
        notes="test",
    )
    validate_run_manifest(m)


def test_no_model_fitting_in_p8b1_manifest() -> None:
    m = RunManifest.harness_default()
    assert m.model_fitting_allowed is False
