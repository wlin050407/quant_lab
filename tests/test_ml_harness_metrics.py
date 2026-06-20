"""Tests for ML-P8B.0 harness metrics."""

from __future__ import annotations

import numpy as np
import pytest

from quant_lab.ml.harness.metrics import (
    compute_p0_regression_metrics,
    compute_p1_binary_metrics,
    compute_p2_multiclass_metrics,
)


def test_p0_regression_metrics_hand_computed() -> None:
    y_true = np.array([1.0, -1.0, 0.0, 2.0])
    y_pred = np.array([0.0, 0.0, 0.0, 0.0])
    m = compute_p0_regression_metrics(y_true, y_pred)
    assert m["valid_count"] == 4
    assert m["mae"] == pytest.approx(1.0)
    assert m["rmse"] == pytest.approx(np.sqrt(1.5))
    assert m["median_absolute_error"] == pytest.approx(1.0)
    assert m["within_0.50_EM_accuracy"] == pytest.approx(0.25)


def test_p0_empty_input_no_crash() -> None:
    m = compute_p0_regression_metrics([], [])
    assert m["valid_count"] == 0
    assert m["mae"] is None


def test_p0_nan_handling() -> None:
    y_true = np.array([1.0, np.nan, 3.0])
    y_pred = np.array([1.0, 2.0, np.nan])
    m = compute_p0_regression_metrics(y_true, y_pred)
    assert m["valid_count"] == 1
    assert m["mae"] == pytest.approx(0.0)


def test_p1_binary_metrics_and_confusion() -> None:
    y_true = np.array([True, False, True, False])
    y_pred = np.array([True, False, False, False])
    y_score = np.array([0.9, 0.1, 0.4, 0.2])
    m = compute_p1_binary_metrics(y_true, y_pred, y_score)
    assert m["valid_count"] == 4
    assert m["class_distribution"]["near"] == 2
    assert m["confusion_matrix"]["tp"] == 1
    assert m["confusion_matrix"]["fn"] == 1
    assert m["roc_auc"] is not None
    assert m["pr_auc"] is not None
    assert m["brier_score"] is not None


def test_p1_single_class_skips_auc() -> None:
    y_true = np.array([False, False, False])
    y_pred = np.array([False, False, False])
    m = compute_p1_binary_metrics(y_true, y_pred, np.array([0.1, 0.2, 0.3]))
    assert m["roc_auc"] is None
    assert m["roc_auc_skipped_reason"] == "both_classes_required"


def test_p1_no_scores_skips_auc() -> None:
    m = compute_p1_binary_metrics([True, False], [True, False])
    assert m["roc_auc_skipped_reason"] == "scores_not_provided"


def test_p2_multiclass_metrics() -> None:
    y_true = ["below", "near", "above", "near"]
    y_pred = ["below", "near", "near", "above"]
    m = compute_p2_multiclass_metrics(y_true, y_pred)
    assert m["valid_count"] == 4
    assert m["class_distribution"]["near"] == 2
    assert m["macro_f1"] is not None
    assert m["confusion_matrix"]["near"]["near"] == 1


def test_p2_missing_class_in_split() -> None:
    y_true = ["below", "below"]
    y_pred = ["below", "near"]
    m = compute_p2_multiclass_metrics(y_true, y_pred)
    assert m["class_distribution"]["above"] == 0
    assert m["balanced_accuracy"] is not None
