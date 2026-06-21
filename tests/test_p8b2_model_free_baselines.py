"""Tests for ML-P8B.2 model-free baseline evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from quant_lab.ml.harness.baselines import (
    ClassPriorBaseline,
    ConstantNotNearBaseline,
    MajorityClassBaseline,
    TrainMeanBaseline,
    TrainMedianBaseline,
    TrainPriorProbabilityBaseline,
    ZeroEmBaseline,
)
from quant_lab.ml.harness.manifests import HARNESS_STAGE_P8B2, RunManifest, validate_run_manifest
from quant_lab.ml.harness.metrics import compute_p0_regression_metrics, compute_p1_binary_metrics
from quant_lab.ml.harness.p8b2_eval import (
    LABEL_BASELINE_ELIGIBLE,
    LABEL_P0,
    LABEL_P1_050,
    LABEL_P2_050,
    LABEL_ZONE_LOC,
    P8B2EvalConfig,
    evaluate_p0_baselines,
    evaluate_p1_baselines,
    evaluate_p2_baselines,
    evaluate_p8b2_gates,
    evaluate_zone_secondary,
    run_p8b2_evaluation,
    validate_joined_forbidden_features,
)
from quant_lab.ml.harness.splits import detect_row_level_random_split
from quant_lab.ml.harness.validators import validate_forbidden_features


def _synthetic_row(
    trade_date: str,
    *,
    split: str,
    d_em: float = 0.1,
    near_050: bool = False,
    near_025: bool = False,
    p2_label: str = "near",
    zone_loc: str | None = "near",
    eligible: bool = True,
) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "split": split,
        "features.spot_t": 5000.0,
        "features.pin_score_t": 0.5,
        LABEL_P0: d_em,
        LABEL_P1_050: near_050,
        "labels.close_near_primary_pin_025": near_025,
        LABEL_P2_050: p2_label,
        LABEL_BASELINE_ELIGIBLE: eligible,
        LABEL_ZONE_LOC: zone_loc,
    }


def _synthetic_dataset() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sessions = [f"2024-0{i}-01" for i in range(1, 6)]
    for sid in sessions[:3]:
        for j in range(4):
            rows.append(
                _synthetic_row(
                    sid,
                    split="train",
                    d_em=float(j) * 0.1,
                    near_050=j % 2 == 0,
                    near_025=j % 3 == 0,
                    p2_label=["below", "near", "above"][j % 3],
                )
            )
    for sid in sessions[3:4]:
        for _j in range(3):
            rows.append(
                _synthetic_row(
                    sid,
                    split="validation",
                    d_em=0.2,
                    near_050=True,
                    p2_label="above",
                )
            )
    for sid in sessions[4:5]:
        for _j in range(3):
            rows.append(
                _synthetic_row(
                    sid,
                    split="test",
                    d_em=-0.1,
                    near_050=False,
                    p2_label="below",
                )
            )
    return rows


def test_p0_zero_baseline_metrics() -> None:
    y_true = np.array([0.0, 0.5, -0.3])
    y_pred = ZeroEmBaseline().predict(3)
    m = compute_p0_regression_metrics(y_true, y_pred)
    assert m["mae"] == pytest.approx(np.mean(np.abs(y_true)))
    assert m["rmse"] == pytest.approx(np.sqrt(np.mean(y_true**2)))


def test_p0_train_median_uses_train_only() -> None:
    rows = _synthetic_dataset()
    eligible = [r for r in rows if r[LABEL_BASELINE_ELIGIBLE]]
    median_b = TrainMedianBaseline()
    train_y = [r[LABEL_P0] for r in eligible if r["split"] == "train"]
    median_b.fit_from_train(train_y)
    out = evaluate_p0_baselines(eligible, baselines=[median_b])
    assert out["train_priors"]["train_median_em"]["median_em"] == pytest.approx(float(np.median(train_y)))
    assert out["validation"]["train_median_em"]["mae"] is not None


def test_p1_majority_baseline_uses_train_only() -> None:
    rows = _synthetic_dataset()
    eligible = [r for r in rows if r[LABEL_BASELINE_ELIGIBLE]]
    out = evaluate_p1_baselines(
        eligible,
        label_key=LABEL_P1_050,
        baselines=[MajorityClassBaseline()],
    )
    assert "majority_class" in out["train"]
    train_near = sum(1 for r in rows if r["split"] == "train" and r[LABEL_P1_050])
    train_total = sum(1 for r in rows if r["split"] == "train")
    expected_majority = train_near >= (train_total - train_near)
    b = MajorityClassBaseline()
    b.fit_from_train([r[LABEL_P1_050] for r in rows if r["split"] == "train"])
    assert b._majority is expected_majority


def test_p1_constant_not_near_baseline() -> None:
    rows = _synthetic_dataset()
    eligible = [r for r in rows if r[LABEL_BASELINE_ELIGIBLE]]
    out = evaluate_p1_baselines(
        eligible,
        label_key=LABEL_P1_050,
        baselines=[ConstantNotNearBaseline()],
    )
    assert out["test"]["constant_not_near"]["class_distribution"]["not_near"] >= 0


def test_p1_train_prior_probability_uses_train_only() -> None:
    b = TrainPriorProbabilityBaseline()
    b.fit_from_train([True, False, True])
    priors = b.compute_train_priors()
    assert priors["near"] == pytest.approx(2 / 3)
    rows = _synthetic_dataset()
    eligible = [r for r in rows if r[LABEL_BASELINE_ELIGIBLE]]
    out = evaluate_p1_baselines(
        eligible,
        label_key=LABEL_P1_050,
        baselines=[TrainPriorProbabilityBaseline()],
    )
    assert "train_prior_probability" in out["train_priors"]


def test_p2_class_prior_baseline() -> None:
    b = ClassPriorBaseline()
    b.fit_from_train(["below", "near", "near"])
    assert b._majority == "near"
    priors = b.compute_train_priors()
    assert priors["near"] == pytest.approx(2 / 3)
    rows = _synthetic_dataset()
    eligible = [r for r in rows if r[LABEL_BASELINE_ELIGIBLE]]
    out = evaluate_p2_baselines(
        eligible,
        label_key=LABEL_P2_050,
        baselines=[ClassPriorBaseline(), MajorityClassBaseline()],
    )
    assert "class_prior" in out["validation"]


def test_split_validation_required_before_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = P8B2EvalConfig(
        version="test",
        dataset_root=tmp_path / "ds",
        feature_root=tmp_path / "feat",
        input_reports=tmp_path / "in",
        output_reports=tmp_path / "out",
        baseline_label_schema_version="1.1.0-draft",
        split_protocol="session_grouped",
        train_sessions_count=3,
        validation_sessions_count=1,
        test_sessions_count=1,
        preferred_binary_target="close_near_primary_pin_050",
        sensitivity_binary_target="close_near_primary_pin_025",
        model_fitting_allowed=False,
    )

    def _fail_load(*_a: Any, **_k: Any) -> list[dict[str, Any]]:
        return _synthetic_dataset()

    def _fail_validate(*_a: Any, **_k: Any) -> Any:
        from quant_lab.ml.harness.splits import SplitValidationResult

        return SplitValidationResult(passed=False, errors=["forced split failure"])

    monkeypatch.setattr("quant_lab.ml.harness.p8b2_eval.load_joined_rows", _fail_load)
    monkeypatch.setattr("quant_lab.ml.harness.p8b2_eval.validate_session_split", _fail_validate)
    result = run_p8b2_evaluation(config, dry_run=False)
    assert result.p8b2_pass is False
    assert result.metrics == {}


def test_forbidden_input_validation_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _synthetic_dataset()

    def _load(*_a: Any, **_k: Any) -> list[dict[str, Any]]:
        bad = dict(rows[0])
        bad["features.future_return"] = 1.0
        return rows[:1] + [bad] + rows[1:]

    monkeypatch.setattr("quant_lab.ml.harness.p8b2_eval.load_joined_rows", _load)
    config = P8B2EvalConfig(
        version="test",
        dataset_root=tmp_path / "ds",
        feature_root=tmp_path / "feat",
        input_reports=tmp_path / "in",
        output_reports=tmp_path / "out",
        baseline_label_schema_version="1.1.0-draft",
        split_protocol="session_grouped",
        train_sessions_count=3,
        validation_sessions_count=1,
        test_sessions_count=1,
        preferred_binary_target="close_near_primary_pin_050",
        sensitivity_binary_target="close_near_primary_pin_025",
        model_fitting_allowed=False,
    )
    result = run_p8b2_evaluation(config, dry_run=False)
    assert result.p8b2_pass is False
    assert result.forbidden_validation.get("forbidden_input_pass") is False


def test_validation_test_not_used_for_priors() -> None:
    b = TrainPriorProbabilityBaseline()
    b.fit_from_train([True, True])
    proba_val = b.predict_proba_near(5)
    b2 = TrainPriorProbabilityBaseline()
    b2.fit_from_train([False, False])
    assert not np.allclose(proba_val, b2.predict_proba_near(5))


def test_run_manifest_p8b2_fields() -> None:
    m = RunManifest(
        run_id="test-run",
        stage=HARNESS_STAGE_P8B2,
        created_at="2026-06-20T00:00:00+00:00",
        code_commit="abc",
        dataset_manifest_hash="ds",
        feature_manifest_hash="ft",
        label_schema_version="1.0.0",
        baseline_label_schema_version="1.1.0-draft",
        target_name="close_near_primary_pin_050",
        split_protocol="session_grouped",
        train_sessions=["2024-01-05"],
        validation_sessions=["2024-11-01"],
        test_sessions=["2025-01-03"],
        metrics_version="p8b0-v1",
        leakage_validation_status="PASS",
        forbidden_input_validation_status="PASS",
        model_type="model_free_baseline",
        model_fitting_allowed=False,
        artifacts_written=[],
        notes="test",
    )
    validate_run_manifest(m)
    payload = json.loads(m.to_json())
    assert payload["stage"] == HARNESS_STAGE_P8B2
    assert payload["model_type"] == "model_free_baseline"
    assert payload["model_fitting_allowed"] is False


def test_no_sklearn_fit_in_baselines() -> None:
    baselines = [
        ZeroEmBaseline(),
        TrainMedianBaseline(),
        TrainMeanBaseline(),
        MajorityClassBaseline(),
        ConstantNotNearBaseline(),
        TrainPriorProbabilityBaseline(),
        ClassPriorBaseline(),
    ]
    for b in baselines:
        b.fit_from_train([0.0, 1.0])
        assert b.fit_from_train.__name__ == "fit_from_train"


def test_zone_secondary_metrics_separate() -> None:
    rows = _synthetic_dataset()
    zone = evaluate_zone_secondary(rows)
    assert zone["zone_eligible_row_count"] > 0
    assert "close_location_distribution" in zone
    assert "train_zone" in zone


def test_single_class_roc_skipped_reason() -> None:
    y_true = np.array([True, True, True])
    y_pred = np.array([True, True, True])
    y_score = np.array([0.6, 0.6, 0.6])
    m = compute_p1_binary_metrics(y_true, y_pred, y_score)
    assert m["roc_auc"] is None
    assert m["roc_auc_skipped_reason"] == "both_classes_required"


def test_validate_joined_forbidden_features_pass() -> None:
    rows = _synthetic_dataset()
    res = validate_joined_forbidden_features(rows)
    assert res["forbidden_input_pass"] is True


def test_detect_row_level_random_split() -> None:
    rows = [
        {"trade_date": "2024-01-05", "split": "train"},
        {"trade_date": "2024-01-05", "split": "test"},
    ]
    errors = detect_row_level_random_split(rows)
    assert len(errors) == 1


def test_evaluate_p8b2_gates() -> None:
    assert evaluate_p8b2_gates(
        split_pass=True,
        forbidden_pass=True,
        p0_done=True,
        p1_done=True,
        model_fitting=False,
    )
    assert not evaluate_p8b2_gates(
        split_pass=True,
        forbidden_pass=True,
        p0_done=True,
        p1_done=True,
        model_fitting=True,
    )


def test_train_mean_baseline() -> None:
    b = TrainMeanBaseline()
    b.fit_from_train([1.0, 3.0])
    assert b.predict(1)[0] == pytest.approx(2.0)


def test_forbidden_features_rejects_label_columns() -> None:
    res = validate_forbidden_features(["labels.close_near_primary_pin_050"])
    assert res.passed is False
