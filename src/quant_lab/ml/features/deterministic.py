"""Deterministic bundle + distance-normalized features."""

from __future__ import annotations

from typing import Any

import numpy as np

from quant_lab.data.point_in_time_replay import DeterministicBundle
from quant_lab.ml.schemas import AsOfContext


def compute_deterministic_features(
    ctx: AsOfContext,
    bundle: DeterministicBundle,
    *,
    call_gex: float | None = None,
    put_gex: float | None = None,
) -> dict[str, Any]:
    spot = ctx.spot_t
    em = ctx.expected_move_t
    out: dict[str, Any] = {
        "spot_t": spot,
        "primary_pin_t": ctx.primary_pin_t,
        "secondary_pin_t": ctx.secondary_pin_t,
        "zone_low_t": ctx.zone_low_t,
        "zone_high_t": ctx.zone_high_t,
        "zone_center_t": ctx.zone_center_t,
        "pin_score_t": ctx.pin_score_t,
        "expected_move_t": em,
        "gamma_source": ctx.gamma_source,
        "oi_semantics_status": ctx.oi_semantics_status,
        "net_gex": bundle.net_gex,
        "king_node": bundle.king_node,
        "call_wall": bundle.call_wall,
        "put_wall": bundle.put_wall,
        "gamma_flip": bundle.flip_level,
    }

    if call_gex is not None and put_gex is not None:
        out["call_gex"] = call_gex
        out["put_gex"] = put_gex
        out["absolute_gex"] = abs(call_gex) + abs(put_gex)
    else:
        out["call_gex"] = None
        out["put_gex"] = None
        out["absolute_gex"] = abs(bundle.net_gex) if np.isfinite(bundle.net_gex) else None

    if ctx.has_valid_zone and ctx.zone_low_t is not None and ctx.zone_high_t is not None:
        width = ctx.zone_high_t - ctx.zone_low_t
        out["zone_width_points"] = width
        out["zone_width_pct"] = width / spot * 100.0 if spot > 0 else None
        out["zone_width_em"] = width / em if em and em > 0 else None
    else:
        out["zone_width_points"] = None
        out["zone_width_pct"] = None
        out["zone_width_em"] = None

    out.update(_distance_features(ctx))
    return out


def _distance_features(ctx: AsOfContext) -> dict[str, Any]:
    spot = ctx.spot_t
    em = ctx.expected_move_t
    out: dict[str, Any] = {}

    def dist(name: str, target: float | None) -> None:
        if target is None or not np.isfinite(spot):
            out[f"distance_spot_to_{name}_points"] = None
            out[f"distance_spot_to_{name}_pct"] = None
            out[f"distance_spot_to_{name}_em"] = None
            return
        pts = spot - target
        out[f"distance_spot_to_{name}_points"] = pts
        out[f"distance_spot_to_{name}_pct"] = pts / spot * 100.0 if spot > 0 else None
        out[f"distance_spot_to_{name}_em"] = pts / em if em and em > 0 else None

    dist("primary_pin", ctx.primary_pin_t)
    dist("secondary_pin", ctx.secondary_pin_t)
    dist("zone_center", ctx.zone_center_t)

    if ctx.zone_low_t is not None:
        out["distance_spot_to_zone_low_points"] = spot - ctx.zone_low_t
    else:
        out["distance_spot_to_zone_low_points"] = None
    if ctx.zone_high_t is not None:
        out["distance_spot_to_zone_high_points"] = spot - ctx.zone_high_t
    else:
        out["distance_spot_to_zone_high_points"] = None

    if (
        ctx.has_valid_zone
        and ctx.zone_low_t is not None
        and ctx.zone_high_t is not None
        and ctx.zone_high_t > ctx.zone_low_t
    ):
        out["spot_position_in_zone"] = (spot - ctx.zone_low_t) / (ctx.zone_high_t - ctx.zone_low_t)
    else:
        out["spot_position_in_zone"] = None

    return out
