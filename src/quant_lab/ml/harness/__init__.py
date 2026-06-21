"""ML-P8B.0 modeling harness — metrics, splits, validators, manifests, baselines."""

from quant_lab.ml.harness.baselines import (
    ClassPriorBaseline,
    ConstantNotNearBaseline,
    MajorityClassBaseline,
    TrainMeanBaseline,
    TrainMedianBaseline,
    TrainPriorProbabilityBaseline,
    ZeroEmBaseline,
)
from quant_lab.ml.harness.manifests import (
    HARNESS_STAGE_P8B2,
    RunManifest,
    validate_run_manifest,
)
from quant_lab.ml.harness.metrics import (
    compute_p0_regression_metrics,
    compute_p1_binary_metrics,
    compute_p2_multiclass_metrics,
)
from quant_lab.ml.harness.splits import SplitValidationResult, validate_session_split
from quant_lab.ml.harness.validators import ForbiddenInputResult, validate_forbidden_features

__all__ = [
    "ClassPriorBaseline",
    "ConstantNotNearBaseline",
    "ForbiddenInputResult",
    "HARNESS_STAGE_P8B2",
    "MajorityClassBaseline",
    "RunManifest",
    "SplitValidationResult",
    "TrainMeanBaseline",
    "TrainMedianBaseline",
    "TrainPriorProbabilityBaseline",
    "ZeroEmBaseline",
    "compute_p0_regression_metrics",
    "compute_p1_binary_metrics",
    "compute_p2_multiclass_metrics",
    "validate_forbidden_features",
    "validate_run_manifest",
    "validate_session_split",
]
