"""Tests for ML-P8B.0 model-free baselines."""

from __future__ import annotations

import numpy as np
import pytest

from quant_lab.ml.harness.baselines import (
    ConstantNotNearBaseline,
    MajorityClassBaseline,
    TrainMedianBaseline,
    TrainPriorProbabilityBaseline,
    ZeroEmBaseline,
)


def test_zero_em_baseline() -> None:
    b = ZeroEmBaseline()
    b.fit_from_train([1.0, -2.0])
    pred = b.predict(3)
    assert np.allclose(pred, 0.0)


def test_train_median_baseline_uses_train_only() -> None:
    b = TrainMedianBaseline()
    b.fit_from_train([1.0, 3.0, 5.0])
    assert b.predict(2)[0] == pytest.approx(3.0)
    with pytest.raises(RuntimeError):
        TrainMedianBaseline().predict(1)


def test_majority_class_baseline() -> None:
    b = MajorityClassBaseline()
    b.fit_from_train([True, False, False])
    pred = b.predict(2)
    assert pred[0] is False


def test_constant_not_near_baseline() -> None:
    b = ConstantNotNearBaseline()
    b.fit_from_train([True, True])
    assert b.predict(2).tolist() == [False, False]


def test_train_prior_probability_baseline() -> None:
    b = TrainPriorProbabilityBaseline()
    b.fit_from_train([True, False, True, False])
    priors = b.compute_train_priors()
    assert priors["near"] == pytest.approx(0.5)
    assert b.predict_proba_near(2).tolist() == [0.5, 0.5]
    labels = b.predict_constant_from_train_prior(3, threshold=0.5)
    assert labels.tolist() == [True, True, True]
