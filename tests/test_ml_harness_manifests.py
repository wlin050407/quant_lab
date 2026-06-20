"""Tests for ML-P8B.0 run manifest schema."""

from __future__ import annotations

import json

import pytest

from quant_lab.ml.harness.manifests import (
    HARNESS_STAGE_P8B0,
    RunManifest,
    RunManifestError,
    validate_run_manifest,
)


def test_run_manifest_default_p8b0() -> None:
    m = RunManifest.harness_default(code_commit="abc123", notes="harness test")
    assert m.stage == HARNESS_STAGE_P8B0
    assert m.model_fitting_allowed is False
    assert m.model_type == "model_free_or_harness_only"
    validate_run_manifest(m)


def test_run_manifest_json_serializable() -> None:
    m = RunManifest.harness_default()
    payload = json.loads(m.to_json())
    assert payload["model_fitting_allowed"] is False
    assert "run_id" in payload


def test_missing_required_field_raises() -> None:
    m = RunManifest.harness_default().to_dict()
    del m["target_name"]
    with pytest.raises(RunManifestError, match="missing required"):
        validate_run_manifest(m)


def test_p8b0_cannot_allow_model_fitting() -> None:
    m = RunManifest.harness_default().to_dict()
    m["model_fitting_allowed"] = True
    with pytest.raises(RunManifestError, match="model_fitting_allowed"):
        validate_run_manifest(m)
