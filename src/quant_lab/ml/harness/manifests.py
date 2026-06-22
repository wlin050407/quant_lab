"""Run manifest schema for ML-P8B harness runs."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from quant_lab.ml.harness.metrics import METRICS_VERSION
from quant_lab.ml.schemas import BASELINE_LABEL_SCHEMA_VERSION, LABEL_SCHEMA_VERSION

RUN_MANIFEST_VERSION = "p8b-run-v1"
HARNESS_STAGE_P8B0 = "P8B.0"
HARNESS_STAGE_P8B1 = "ML-P8B.1"
HARNESS_STAGE_P8B2 = "ML-P8B.2"
HARNESS_STAGE_P8B3_1 = "ML-P8B.3.1"
HARNESS_STAGE_P8B3_2 = "ML-P8B.3.2"
HARNESS_STAGE_P8B3_5 = "ML-P8B.3.5"
HARNESS_STAGE_P8B3_7 = "ML-P8B.3.7"
NO_FITTING_STAGES: frozenset[str] = frozenset(
    {
        HARNESS_STAGE_P8B0,
        HARNESS_STAGE_P8B1,
        HARNESS_STAGE_P8B2,
        HARNESS_STAGE_P8B3_1,
        HARNESS_STAGE_P8B3_5,
    }
)

REQUIRED_MANIFEST_FIELDS: tuple[str, ...] = (
    "run_id",
    "stage",
    "created_at",
    "code_commit",
    "dataset_manifest_hash",
    "feature_manifest_hash",
    "label_schema_version",
    "baseline_label_schema_version",
    "target_name",
    "split_protocol",
    "train_sessions",
    "validation_sessions",
    "test_sessions",
    "metrics_version",
    "leakage_validation_status",
    "forbidden_input_validation_status",
    "model_type",
    "model_fitting_allowed",
    "artifacts_written",
    "notes",
)


class RunManifestError(ValueError):
    """Raised when run manifest is invalid."""


@dataclass
class RunManifest:
    run_id: str
    stage: str
    created_at: str
    code_commit: str
    dataset_manifest_hash: str
    feature_manifest_hash: str
    label_schema_version: str
    baseline_label_schema_version: str
    target_name: str
    split_protocol: str
    train_sessions: list[str]
    validation_sessions: list[str]
    test_sessions: list[str]
    metrics_version: str
    leakage_validation_status: str
    forbidden_input_validation_status: str
    model_type: str
    model_fitting_allowed: bool
    artifacts_written: list[str]
    notes: str
    manifest_version: str = RUN_MANIFEST_VERSION

    @classmethod
    def harness_default(
        cls,
        *,
        code_commit: str = "unknown",
        target_name: str = "harness_only",
        notes: str = "",
    ) -> RunManifest:
        """Default P8B.0 manifest — no model fitting."""
        return cls(
            run_id=str(uuid.uuid4()),
            stage=HARNESS_STAGE_P8B0,
            created_at=datetime.now(tz=UTC).isoformat(),
            code_commit=code_commit,
            dataset_manifest_hash="",
            feature_manifest_hash="",
            label_schema_version=LABEL_SCHEMA_VERSION,
            baseline_label_schema_version=BASELINE_LABEL_SCHEMA_VERSION,
            target_name=target_name,
            split_protocol="session_grouped",
            train_sessions=[],
            validation_sessions=[],
            test_sessions=[],
            metrics_version=METRICS_VERSION,
            leakage_validation_status="not_run",
            forbidden_input_validation_status="not_run",
            model_type="model_free_or_harness_only",
            model_fitting_allowed=False,
            artifacts_written=[],
            notes=notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def validate_run_manifest(manifest: RunManifest | dict[str, Any]) -> None:
    """Raise RunManifestError if required fields missing or P8B.0 invariants violated."""
    data = manifest.to_dict() if isinstance(manifest, RunManifest) else dict(manifest)
    missing = [f for f in REQUIRED_MANIFEST_FIELDS if f not in data]
    if missing:
        raise RunManifestError(f"missing required manifest fields: {missing}")
    for field_name in REQUIRED_MANIFEST_FIELDS:
        if data[field_name] is None:
            raise RunManifestError(f"required field is null: {field_name}")
    if data.get("stage") in NO_FITTING_STAGES and data.get("model_fitting_allowed") is True:
        raise RunManifestError(f"{data.get('stage')} manifests must have model_fitting_allowed=false")
    if data.get("model_type") == "model_free_or_harness_only" and data.get("model_fitting_allowed"):
        raise RunManifestError("model_free_or_harness_only cannot have model_fitting_allowed=true")
