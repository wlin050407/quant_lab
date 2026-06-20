"""Supervised label functions for ML-P6 (future outcomes only, no feature leakage)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import pandas as pd

from quant_lab.ml.schemas import (
    BASELINE_LABEL_SCHEMA_VERSION,
    AsOfContext,
    LabelRow,
    OutcomeContext,
)

CloseLocation = Literal["below", "inside", "above"]
ExitDirection = Literal["up", "down"]
BaselineDirection = Literal["below", "near", "above"]

BASELINE_NEAR_THRESHOLDS_EM: tuple[float, ...] = (0.25, 0.50)


@dataclass(frozen=True)
class PinToleranceConfig:
    """Tolerance presets for strike-pin proximity labels."""

    fixed_points: float | None = None
    spot_pct: float | None = None
    remaining_em_fraction: float | None = None

    def tolerance_points(self, spot: float, remaining_em: float | None) -> float | None:
        candidates: list[float] = []
        if self.fixed_points is not None:
            candidates.append(self.fixed_points)
        if self.spot_pct is not None:
            candidates.append(spot * self.spot_pct / 100.0)
        if self.remaining_em_fraction is not None and remaining_em is not None and remaining_em > 0:
            candidates.append(remaining_em * self.remaining_em_fraction)
        if not candidates:
            return None
        return min(candidates)


DEFAULT_PIN_TOLERANCE_CONFIGS: dict[str, PinToleranceConfig] = {
    "fixed_2.5pt": PinToleranceConfig(fixed_points=2.5),
    "fixed_5pt": PinToleranceConfig(fixed_points=5.0),
    "spot_0.05pct": PinToleranceConfig(spot_pct=0.05),
    "spot_0.10pct": PinToleranceConfig(spot_pct=0.10),
    "em_0.05": PinToleranceConfig(remaining_em_fraction=0.05),
    "em_0.10": PinToleranceConfig(remaining_em_fraction=0.10),
}


def remaining_expected_move(expected_move_t: float, as_of: datetime, session_close: datetime) -> float | None:
    """Scale full-session expected move by remaining session fraction (frozen contract)."""
    if expected_move_t is None or math.isnan(expected_move_t) or expected_move_t <= 0:
        return None
    total = (session_close - as_of.replace(hour=9, minute=30, second=0, microsecond=0)).total_seconds()
    if total <= 0:
        return None
    remaining = max((session_close - as_of).total_seconds(), 0.0)
    return expected_move_t * math.sqrt(remaining / total) if remaining > 0 else 0.0


def compute_close_location_vs_zone(
    official_close: float,
    zone_low: float | None,
    zone_high: float | None,
) -> str | None:
    if zone_low is None or zone_high is None:
        return None
    if official_close < zone_low:
        return "below"
    if official_close <= zone_high:
        return "inside"
    return "above"


def compute_close_inside_zone(
    official_close: float,
    zone_low: float | None,
    zone_high: float | None,
) -> bool | None:
    if zone_low is None or zone_high is None:
        return None
    return zone_low <= official_close <= zone_high


def compute_normalized_close_move(
    official_close: float,
    spot_t: float,
    remaining_em: float | None,
) -> tuple[float | None, str | None]:
    if remaining_em is None or math.isnan(remaining_em) or remaining_em <= 0:
        return None, "missing_or_invalid_remaining_expected_move"
    return (official_close - spot_t) / remaining_em, None


def compute_close_distance_labels(
    official_close: float,
    ctx: AsOfContext,
    remaining_em: float | None,
) -> dict[str, float | None]:
    out: dict[str, float | None] = {
        "close_distance_to_zone_center_points": None,
        "close_distance_to_zone_center_em": None,
        "close_distance_to_primary_pin_points": None,
        "close_distance_to_primary_pin_em": None,
        "close_distance_to_secondary_pin_points": None,
        "close_distance_to_secondary_pin_em": None,
    }
    if ctx.zone_center_t is not None:
        out["close_distance_to_zone_center_points"] = official_close - ctx.zone_center_t
        if remaining_em and remaining_em > 0:
            out["close_distance_to_zone_center_em"] = (official_close - ctx.zone_center_t) / remaining_em
    if ctx.primary_pin_t is not None:
        out["close_distance_to_primary_pin_points"] = official_close - ctx.primary_pin_t
        if remaining_em and remaining_em > 0:
            out["close_distance_to_primary_pin_em"] = (official_close - ctx.primary_pin_t) / remaining_em
    if ctx.secondary_pin_t is not None:
        out["close_distance_to_secondary_pin_points"] = official_close - ctx.secondary_pin_t
        if remaining_em and remaining_em > 0:
            out["close_distance_to_secondary_pin_em"] = (official_close - ctx.secondary_pin_t) / remaining_em
    return out


def compute_close_distance_to_primary_pin_em(
    official_close: float,
    primary_pin_t: float,
    remaining_expected_move_t: float,
) -> float:
    """P0 baseline regression target (EM-normalized signed distance to primary pin)."""
    return (official_close - primary_pin_t) / remaining_expected_move_t


def evaluate_baseline_target_eligibility(
    *,
    primary_pin_t: float | None,
    remaining_expected_move_t: float | None,
    official_close: float | None,
    label_source_timestamp: datetime | None,
    as_of_timestamp: datetime,
) -> tuple[bool, list[str]]:
    """Return (eligible, exclusion_reasons) for baseline primary-pin track."""
    reasons: list[str] = []
    if primary_pin_t is None or (isinstance(primary_pin_t, float) and math.isnan(primary_pin_t)):
        reasons.append("missing_primary_pin")
    if (
        remaining_expected_move_t is None
        or not math.isfinite(remaining_expected_move_t)
        or remaining_expected_move_t <= 0
    ):
        reasons.append("remaining_em_invalid")
    if official_close is None or (isinstance(official_close, float) and math.isnan(official_close)):
        reasons.append("missing_official_close")
    if label_source_timestamp is None or not isinstance(label_source_timestamp, datetime):
        reasons.append("label_source_not_after_as_of")
    elif label_source_timestamp <= as_of_timestamp:
        reasons.append("label_source_not_after_as_of")
    return len(reasons) == 0, reasons


def compute_baseline_p1_near(d_em: float, threshold_em: float) -> bool:
    """P1 binary: close near primary pin within threshold EM."""
    return abs(d_em) <= threshold_em


def compute_baseline_p2_directional(d_em: float, threshold_em: float) -> BaselineDirection:
    """P2 ternary classification relative to primary pin."""
    if d_em < -threshold_em:
        return "below"
    if abs(d_em) <= threshold_em:
        return "near"
    return "above"


@dataclass(frozen=True)
class BaselinePrimaryPinLabels:
    """Additive v1.1 draft baseline primary-pin labels for one anchor."""

    close_distance_to_primary_pin_points: float | None
    close_distance_to_primary_pin_em: float | None
    close_near_primary_pin_025: bool | None
    close_near_primary_pin_050: bool | None
    close_above_below_primary_pin_025: BaselineDirection | None
    close_above_below_primary_pin_050: BaselineDirection | None
    baseline_target_eligible: bool
    baseline_target_exclusion_reasons: tuple[str, ...]
    baseline_label_schema_version: str


def compute_baseline_primary_pin_labels(
    *,
    official_close: float | None,
    primary_pin_t: float | None,
    remaining_expected_move_t: float | None,
    as_of_timestamp: datetime,
    label_source_timestamp: datetime | None,
) -> BaselinePrimaryPinLabels:
    """Compute additive baseline primary-pin labels (v1.1 draft)."""
    eligible, reasons = evaluate_baseline_target_eligibility(
        primary_pin_t=primary_pin_t,
        remaining_expected_move_t=remaining_expected_move_t,
        official_close=official_close,
        label_source_timestamp=label_source_timestamp,
        as_of_timestamp=as_of_timestamp,
    )
    null_block = BaselinePrimaryPinLabels(
        close_distance_to_primary_pin_points=None,
        close_distance_to_primary_pin_em=None,
        close_near_primary_pin_025=None,
        close_near_primary_pin_050=None,
        close_above_below_primary_pin_025=None,
        close_above_below_primary_pin_050=None,
        baseline_target_eligible=False,
        baseline_target_exclusion_reasons=tuple(reasons),
        baseline_label_schema_version=BASELINE_LABEL_SCHEMA_VERSION,
    )
    if not eligible:
        return null_block

    assert primary_pin_t is not None
    assert remaining_expected_move_t is not None
    assert official_close is not None

    d_points = official_close - primary_pin_t
    d_em = compute_close_distance_to_primary_pin_em(
        official_close, primary_pin_t, remaining_expected_move_t
    )
    return BaselinePrimaryPinLabels(
        close_distance_to_primary_pin_points=d_points,
        close_distance_to_primary_pin_em=d_em,
        close_near_primary_pin_025=compute_baseline_p1_near(d_em, BASELINE_NEAR_THRESHOLDS_EM[0]),
        close_near_primary_pin_050=compute_baseline_p1_near(d_em, BASELINE_NEAR_THRESHOLDS_EM[1]),
        close_above_below_primary_pin_025=compute_baseline_p2_directional(
            d_em, BASELINE_NEAR_THRESHOLDS_EM[0]
        ),
        close_above_below_primary_pin_050=compute_baseline_p2_directional(
            d_em, BASELINE_NEAR_THRESHOLDS_EM[1]
        ),
        baseline_target_eligible=True,
        baseline_target_exclusion_reasons=(),
        baseline_label_schema_version=BASELINE_LABEL_SCHEMA_VERSION,
    )


def _apply_baseline_primary_pin_labels(row: LabelRow, baseline: BaselinePrimaryPinLabels) -> None:
    row.baseline_target_eligible = baseline.baseline_target_eligible
    row.baseline_target_exclusion_reasons = list(baseline.baseline_target_exclusion_reasons)
    row.baseline_label_schema_version = baseline.baseline_label_schema_version
    row.close_distance_to_primary_pin_points = baseline.close_distance_to_primary_pin_points
    row.close_distance_to_primary_pin_em = baseline.close_distance_to_primary_pin_em
    row.close_near_primary_pin_025 = baseline.close_near_primary_pin_025
    row.close_near_primary_pin_050 = baseline.close_near_primary_pin_050
    row.close_above_below_primary_pin_025 = baseline.close_above_below_primary_pin_025
    row.close_above_below_primary_pin_050 = baseline.close_above_below_primary_pin_050


def compute_near_pin(
    official_close: float,
    pin: float | None,
    spot: float,
    remaining_em: float | None,
    config: PinToleranceConfig,
) -> bool | None:
    if pin is None:
        return None
    tol = config.tolerance_points(spot, remaining_em)
    if tol is None:
        return None
    return abs(official_close - pin) <= tol


def compute_near_nearest_strike(
    official_close: float,
    strikes: list[float] | None,
    spot: float,
    remaining_em: float | None,
    config: PinToleranceConfig,
) -> bool | None:
    if not strikes:
        return None
    nearest = min(strikes, key=lambda s: abs(s - official_close))
    return compute_near_pin(official_close, nearest, spot, remaining_em, config)


def _future_path_after_as_of(
    path: pd.DataFrame,
    as_of: datetime,
    horizon_minutes: float | None = None,
) -> pd.DataFrame:
    if path.empty:
        return path
    ts_col = "event_timestamp"
    subset = path[path[ts_col] > as_of].copy()
    if horizon_minutes is not None and not subset.empty:
        end = as_of + timedelta(minutes=horizon_minutes)
        subset = subset[subset[ts_col] <= end]
    return subset.sort_values(ts_col)


def _realized_vol_from_path(prices: pd.Series) -> float | None:
    if len(prices) < 2:
        return None
    rets = prices.pct_change().dropna()
    if rets.empty:
        return None
    return float(rets.std() * math.sqrt(len(rets)))


def compute_forward_realized_vol(
    path: pd.DataFrame,
    as_of: datetime,
    horizon_minutes: float,
) -> float | None:
    subset = _future_path_after_as_of(path, as_of, horizon_minutes)
    if subset.empty:
        return None
    span = (subset["event_timestamp"].max() - as_of).total_seconds() / 60.0
    if span < horizon_minutes * 0.9:
        return None
    return _realized_vol_from_path(subset["price"].astype(float))


def compute_max_excursion_labels(
    path: pd.DataFrame,
    as_of: datetime,
    spot_t: float,
    official_close: float,
) -> dict[str, float | None]:
    future = _future_path_after_as_of(path, as_of)
    if future.empty:
        return {
            "max_upside_before_close_points": None,
            "max_downside_before_close_points": None,
            "max_favorable_excursion_to_close": None,
            "max_adverse_excursion_to_close": None,
        }
    prices = future["price"].astype(float)
    max_price = float(prices.max())
    min_price = float(prices.min())
    max_up = max_price - spot_t
    max_down = spot_t - min_price
    mfe = official_close - spot_t
    mae = spot_t - official_close
    return {
        "max_upside_before_close_points": max_up,
        "max_downside_before_close_points": max_down,
        "max_favorable_excursion_to_close": mfe if mfe > 0 else 0.0,
        "max_adverse_excursion_to_close": mae if mae > 0 else 0.0,
    }


def compute_exit_labels(
    ctx: AsOfContext,
    path: pd.DataFrame,
    as_of: datetime,
    session_close: datetime,
) -> dict[str, Any]:
    """Exit labels from future index path vs zone frozen at as_of."""
    nulls: dict[str, Any] = {
        "first_zone_exit_direction": None,
        "first_zone_exit_timestamp": None,
        "minutes_to_first_exit": None,
        "exit_before_close": None,
        "return_to_zone_after_exit": None,
        "return_to_zone_within_5m": None,
        "return_to_zone_within_15m": None,
        "return_to_zone_within_30m": None,
        "valid_upside_exit_15m": None,
        "valid_downside_exit_15m": None,
        "valid_upside_exit_30m": None,
        "valid_downside_exit_30m": None,
    }
    if not ctx.has_valid_zone or ctx.zone_low_t is None or ctx.zone_high_t is None:
        return {**nulls, "_exclusion": "no_valid_zone_at_as_of"}

    if ctx.spot_zone_state_at_as_of in {"above_break", "below_break"}:
        return {
            **nulls,
            "_exclusion": "already_outside_zone_at_as_of",
            "first_zone_exit_direction": None,
        }

    future = _future_path_after_as_of(path, as_of)
    if future.empty:
        return {**nulls, "_exclusion": "insufficient_future_path"}

    z_low = ctx.zone_low_t
    z_high = ctx.zone_high_t
    up_break = ctx.zone_break_up if ctx.zone_break_up is not None else z_high
    down_break = ctx.zone_break_down if ctx.zone_break_down is not None else z_low

    first_exit_ts: datetime | None = None
    first_dir: ExitDirection | None = None
    for _, row in future.iterrows():
        price = float(row["price"])
        ts = row["event_timestamp"]
        if price > z_high:
            first_exit_ts = ts
            first_dir = "up"
            break
        if price < z_low:
            first_exit_ts = ts
            first_dir = "down"
            break

    out = dict(nulls)
    if first_exit_ts is None or first_dir is None:
        out["exit_before_close"] = False
        return out

    out["first_zone_exit_direction"] = first_dir
    out["first_zone_exit_timestamp"] = first_exit_ts
    out["minutes_to_first_exit"] = (first_exit_ts - as_of).total_seconds() / 60.0
    out["exit_before_close"] = first_exit_ts < session_close

    after_exit = future[future["event_timestamp"] >= first_exit_ts]
    returned = False
    for _, row in after_exit.iterrows():
        price = float(row["price"])
        if z_low <= price <= z_high:
            returned = True
            break
    out["return_to_zone_after_exit"] = returned

    for minutes, key in [(5, "return_to_zone_within_5m"), (15, "return_to_zone_within_15m"), (30, "return_to_zone_within_30m")]:
        window_end = first_exit_ts + timedelta(minutes=minutes)
        window = after_exit[after_exit["event_timestamp"] <= window_end]
        hit = any(z_low <= float(p) <= z_high for p in window["price"])
        out[key] = hit if returned else False

    for horizon, up_key, down_key in [
        (15, "valid_upside_exit_15m", "valid_downside_exit_15m"),
        (30, "valid_upside_exit_30m", "valid_downside_exit_30m"),
    ]:
        horizon_path = _future_path_after_as_of(path, as_of, horizon)
        if horizon_path.empty:
            out[up_key] = None
            out[down_key] = None
            continue
        max_p = float(horizon_path["price"].max())
        min_p = float(horizon_path["price"].min())
        out[up_key] = max_p >= up_break
        out[down_key] = min_p <= down_break

    return out


def compute_all_labels(
    ctx: AsOfContext,
    outcome: OutcomeContext,
    *,
    pin_tolerance_config: PinToleranceConfig | None = None,
    nearest_strikes: list[float] | None = None,
) -> LabelRow:
    """Compute full label row for one anchor."""
    row = LabelRow()
    reasons: list[str] = []
    tol = pin_tolerance_config or DEFAULT_PIN_TOLERANCE_CONFIGS["fixed_5pt"]

    rem_em = remaining_expected_move(
        ctx.expected_move_t,
        ctx.as_of_timestamp,
        outcome.session_close_timestamp,
    )

    if not ctx.has_valid_zone:
        reasons.append("no_valid_zone_at_as_of")

    official_close = outcome.official_close
    row.official_close_source = outcome.official_close_source
    row.label_source_timestamp = outcome.label_source_timestamp()
    row.label_horizon_minutes = (
        outcome.session_close_timestamp - ctx.as_of_timestamp
    ).total_seconds() / 60.0

    if ctx.has_valid_zone:
        row.close_location_vs_current_zone = compute_close_location_vs_zone(
            official_close, ctx.zone_low_t, ctx.zone_high_t
        )
        row.close_inside_current_zone = compute_close_inside_zone(
            official_close, ctx.zone_low_t, ctx.zone_high_t
        )
    else:
        reasons.append("close_location_skipped_no_zone")

    ncm, ncm_reason = compute_normalized_close_move(official_close, ctx.spot_t, rem_em)
    row.normalized_close_move = ncm
    if ncm_reason:
        reasons.append(ncm_reason)

    dist = compute_close_distance_labels(official_close, ctx, rem_em)
    for k, v in dist.items():
        if k not in (
            "close_distance_to_primary_pin_points",
            "close_distance_to_primary_pin_em",
        ):
            setattr(row, k, v)

    baseline = compute_baseline_primary_pin_labels(
        official_close=official_close,
        primary_pin_t=ctx.primary_pin_t,
        remaining_expected_move_t=rem_em,
        as_of_timestamp=ctx.as_of_timestamp,
        label_source_timestamp=row.label_source_timestamp,
    )
    _apply_baseline_primary_pin_labels(row, baseline)

    row.close_near_primary_pin = compute_near_pin(
        official_close, ctx.primary_pin_t, ctx.spot_t, rem_em, tol
    )
    row.close_near_secondary_pin = compute_near_pin(
        official_close, ctx.secondary_pin_t, ctx.spot_t, rem_em, tol
    )
    row.close_near_nearest_strike = compute_near_nearest_strike(
        official_close, nearest_strikes, ctx.spot_t, rem_em, tol
    )

    exit_labels = compute_exit_labels(
        ctx, outcome.future_index_path, ctx.as_of_timestamp, outcome.session_close_timestamp
    )
    excl = exit_labels.pop("_exclusion", None)
    if excl:
        reasons.append(str(excl))
    for k, v in exit_labels.items():
        if hasattr(row, k):
            setattr(row, k, v)

    path = outcome.future_index_path
    for minutes, attr in [
        (5, "realized_vol_5m_forward"),
        (15, "realized_vol_15m_forward"),
        (30, "realized_vol_30m_forward"),
    ]:
        vol = compute_forward_realized_vol(path, ctx.as_of_timestamp, minutes)
        setattr(row, attr, vol)
        if vol is None and not path.empty:
            reasons.append(f"insufficient_horizon_for_{attr}")

    exc = compute_max_excursion_labels(
        path, ctx.as_of_timestamp, ctx.spot_t, official_close
    )
    for k, v in exc.items():
        setattr(row, k, v)

    row.exclusion_reasons = reasons
    return row
