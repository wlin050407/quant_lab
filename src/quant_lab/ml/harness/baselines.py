"""Model-free baseline interfaces for ML-P8B harness (no sklearn .fit())."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np


class ModelFreeBaseline(ABC):
    """Base class for deterministic / train-prior baselines."""

    name: str

    @abstractmethod
    def fit_from_train(self, y_train: Any) -> None:
        """Compute statistics from training labels only."""

    @abstractmethod
    def predict(self, n: int) -> np.ndarray:
        """Return predictions for n rows."""


@dataclass
class ZeroEmBaseline(ModelFreeBaseline):
    """P0 baseline: always predict 0 EM."""

    name: str = "zero_em"

    def fit_from_train(self, y_train: Any) -> None:
        return None

    def predict(self, n: int) -> np.ndarray:
        return np.zeros(n, dtype=float)


@dataclass
class TrainMedianBaseline(ModelFreeBaseline):
    """P0 baseline: predict train-set median d_em."""

    name: str = "train_median_em"
    _median: float = 0.0
    _fitted: bool = field(default=False, repr=False)

    def fit_from_train(self, y_train: Any) -> None:
        arr = np.asarray(y_train, dtype=float)
        valid = arr[np.isfinite(arr)]
        if valid.size == 0:
            self._median = 0.0
        else:
            self._median = float(np.median(valid))
        self._fitted = True

    def predict(self, n: int) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("call fit_from_train before predict")
        return np.full(n, self._median, dtype=float)

    def reset(self) -> None:
        self._median = 0.0
        self._fitted = False


@dataclass
class MajorityClassBaseline(ModelFreeBaseline):
    """P1/P2 baseline: predict train majority class."""

    name: str = "majority_class"
    _majority: Any = False
    _fitted: bool = field(default=False, repr=False)

    def fit_from_train(self, y_train: Any) -> None:
        arr = np.asarray(y_train, dtype=object)
        valid = [v for v in arr if v is not None]
        if not valid:
            self._majority = False
        else:
            counts: dict[Any, int] = {}
            for v in valid:
                counts[v] = counts.get(v, 0) + 1
            self._majority = max(counts, key=lambda k: counts[k])
        self._fitted = True

    def predict(self, n: int) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("call fit_from_train before predict")
        return np.full(n, self._majority, dtype=object)


@dataclass
class ConstantNotNearBaseline(ModelFreeBaseline):
    """P1 baseline: always predict not_near (False)."""

    name: str = "constant_not_near"

    def fit_from_train(self, y_train: Any) -> None:
        return None

    def predict(self, n: int) -> np.ndarray:
        return np.zeros(n, dtype=bool)


@dataclass
class TrainPriorProbabilityBaseline(ModelFreeBaseline):
    """P1 baseline: constant probability = train P(near); predict label via threshold 0.5."""

    name: str = "train_prior_probability"
    _prior_near: float = 0.0
    _fitted: bool = field(default=False, repr=False)

    def fit_from_train(self, y_train: Any) -> None:
        arr = np.asarray(y_train, dtype=bool)
        valid = arr[np.isfinite(arr.astype(float))] if arr.dtype != bool else arr
        if valid.size == 0:
            self._prior_near = 0.0
        else:
            self._prior_near = float(np.mean(valid.astype(bool)))
        self._fitted = True

    def compute_train_priors(self) -> dict[str, float]:
        if not self._fitted:
            raise RuntimeError("call fit_from_train before compute_train_priors")
        return {"near": self._prior_near, "not_near": 1.0 - self._prior_near}

    def predict_proba_near(self, n: int) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("call fit_from_train before predict_proba_near")
        return np.full(n, self._prior_near, dtype=float)

    def predict_constant_from_train_prior(self, n: int, *, threshold: float = 0.5) -> np.ndarray:
        return self.predict_proba_near(n) >= threshold

    def predict(self, n: int) -> np.ndarray:
        return self.predict_constant_from_train_prior(n)

    def reset(self) -> None:
        self._prior_near = 0.0
        self._fitted = False
