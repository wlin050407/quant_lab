"""Simple learned model specs for ML-P8B.3 (metadata only — no estimator instantiation)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TrackKind = Literal["P0", "P1", "P2"]


@dataclass(frozen=True)
class ModelSpec:
    """Base metadata for a simple sklearn model spec (no fitting in P8B.3.1)."""

    name: str
    track: TrackKind
    target_key: str
    sklearn_estimator: str
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    optional: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class P0LinearRegressionSpec(ModelSpec):
    """P0: LinearRegression on close_distance_to_primary_pin_em."""

    name: str = "p0_linear_regression"
    track: TrackKind = "P0"
    target_key: str = "labels.close_distance_to_primary_pin_em"
    sklearn_estimator: str = "sklearn.linear_model.LinearRegression"
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    optional: bool = False


@dataclass(frozen=True)
class P0RidgeRegressionSpec(ModelSpec):
    """P0: Ridge regression on close_distance_to_primary_pin_em."""

    name: str = "p0_ridge_regression"
    track: TrackKind = "P0"
    target_key: str = "labels.close_distance_to_primary_pin_em"
    sklearn_estimator: str = "sklearn.linear_model.Ridge"
    hyperparameters: dict[str, Any] = field(default_factory=lambda: {"alpha": 1.0})
    optional: bool = False


@dataclass(frozen=True)
class P1LogisticRegressionSpec(ModelSpec):
    """P1: LogisticRegression for binary near/not_near targets."""

    name: str = "p1_logistic_regression"
    track: TrackKind = "P1"
    target_key: str = "labels.close_near_primary_pin_050"
    sklearn_estimator: str = "sklearn.linear_model.LogisticRegression"
    hyperparameters: dict[str, Any] = field(
        default_factory=lambda: {
            "C": 1.0,
            "max_iter": 1000,
            "class_weight": None,
            "threshold": 0.5,
        }
    )
    optional: bool = False


@dataclass(frozen=True)
class P2MultinomialLogisticRegressionSpec(ModelSpec):
    """P2 optional: multinomial LogisticRegression."""

    name: str = "p2_multinomial_logistic_regression"
    track: TrackKind = "P2"
    target_key: str = "labels.close_above_below_primary_pin_050"
    sklearn_estimator: str = "sklearn.linear_model.LogisticRegression"
    hyperparameters: dict[str, Any] = field(
        default_factory=lambda: {
            "C": 1.0,
            "max_iter": 1000,
            "multi_class": "multinomial",
        }
    )
    optional: bool = True


def default_p0_specs() -> list[ModelSpec]:
    return [P0LinearRegressionSpec(), P0RidgeRegressionSpec()]


def default_p1_specs(*, include_sensitivity: bool = True) -> list[ModelSpec]:
    specs: list[ModelSpec] = [
        P1LogisticRegressionSpec(
            name="p1_logistic_050",
            target_key="labels.close_near_primary_pin_050",
        ),
    ]
    if include_sensitivity:
        specs.append(
            P1LogisticRegressionSpec(
                name="p1_logistic_025",
                target_key="labels.close_near_primary_pin_025",
            )
        )
    return specs


def default_p2_specs(*, include_025: bool = True) -> list[ModelSpec]:
    specs: list[ModelSpec] = [
        P2MultinomialLogisticRegressionSpec(
            name="p2_multinomial_050",
            target_key="labels.close_above_below_primary_pin_050",
        ),
    ]
    if include_025:
        specs.append(
            P2MultinomialLogisticRegressionSpec(
                name="p2_multinomial_025",
                target_key="labels.close_above_below_primary_pin_025",
            )
        )
    return specs


def all_allowed_model_specs(*, include_p2: bool = True) -> list[ModelSpec]:
    specs = default_p0_specs() + default_p1_specs()
    if include_p2:
        specs.extend(default_p2_specs())
    return specs
