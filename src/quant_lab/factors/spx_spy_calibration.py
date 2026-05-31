"""SPY → SPX GEX proxy and paired-day calibration.

SPX 0DTE is the trading target; 18-year history lives on SPY (Philipp Dubach).
This module bridges the two without requiring a long ^SPX archive.

## Default mode: **theoretical proxy**

If dealer positioning shape is similar, aggregated GEX scales roughly with S²:

    k_theoretical ≈ (S_spx / S_spy)²

Regime (long/short gamma) and flip level map as:

    regime_spx  = regime_spy
    flip_spx    ≈ flip_spy × (S_spx / S_spy)   # ≈ 10× for index vs ETF

## Empirical mode: **paired EoD snapshots**

When the same calendar date has both ``SPY`` and ``^SPX`` chains on disk,
``calibrate_paired_day`` estimates k = GEX_spx / GEX_spy.

**Warning:** yfinance ``^SPX`` chains often have sparse open interest (tens of
rows vs thousands on SPY). Empirical k is only accepted when the SPX chain
passes ``spx_chain_usable()``; otherwise we fall back to the theoretical proxy.

Persist calibrated knobs in ``config/spx_spy_calibration.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from quant_lab.config import settings
from quant_lab.factors.calibration import GEXSnapshot

DEFAULT_SPY_SYMBOL = "SPY"
DEFAULT_SPX_SYMBOL = "^SPX"
DEFAULT_STRIKE_SCALE = 10.0
DEFAULT_MIN_SPX_OI_ROWS = 100


@dataclass(frozen=True)
class SPXCalibrationParams:
    """Knobs for SPY → SPX GEX mapping."""

    gex_scale_k: float | None  # None → use (S_spx/S_spy)² per day
    strike_scale: float = DEFAULT_STRIKE_SCALE
    min_spx_oi_rows: int = DEFAULT_MIN_SPX_OI_ROWS
    n_paired_days: int = 0
    paired_dates: tuple[str, ...] = ()
    method: str = "theoretical_proxy"  # or "empirical_median"


@dataclass(frozen=True)
class SPXGEXProxy:
    """SPX GEX estimate derived from a SPY snapshot."""

    date: str
    spy_spot: float
    spx_spot: float
    net_gex_bn_per_1pct: float
    flip_level: float
    spot_above_flip: bool
    regime: str
    gex_scale_k: float
    method: str


@dataclass(frozen=True)
class PairedDayCalibration:
    date: str
    spy_spot: float
    spx_spot: float
    strike_scale: float
    gex_scale_k: float
    flip_scale: float | None
    regime_match: bool
    spx_usable: bool
    spy_net_gex_bn: float
    spx_net_gex_bn: float


@dataclass(frozen=True)
class SPXChainQuality:
    rows: int
    oi_rows: int
    usable: bool


def theoretical_gex_scale(spy_spot: float, spx_spot: float) -> float:
    """GEX ratio if chain shape is identical (GEX ∝ S²)."""
    if spy_spot <= 0 or spx_spot <= 0:
        raise ValueError(f"spots must be positive: spy={spy_spot}, spx={spx_spot}")
    return float((spx_spot / spy_spot) ** 2)


def theoretical_strike_scale(spy_spot: float, spx_spot: float) -> float:
    """Strike / flip scale from spot ratio."""
    if spy_spot <= 0:
        raise ValueError(f"spy_spot must be positive: {spy_spot}")
    return float(spx_spot / spy_spot)


def spx_chain_usable(
    chain_rows: int,
    oi_rows: int,
    *,
    min_oi_rows: int = DEFAULT_MIN_SPX_OI_ROWS,
) -> bool:
    """Return True when ^SPX chain has enough OI to trust empirical GEX."""
    return oi_rows >= min_oi_rows and chain_rows > 0


def spx_chain_quality(
    open_interest: Any,
    *,
    min_oi_rows: int = DEFAULT_MIN_SPX_OI_ROWS,
) -> SPXChainQuality:
    """Summarize ^SPX chain OI coverage."""
    oi = np.asarray(open_interest, dtype=float)
    rows = int(len(oi))
    oi_rows = int(np.sum(oi > 0))
    usable = spx_chain_usable(rows, oi_rows, min_oi_rows=min_oi_rows)
    return SPXChainQuality(rows=rows, oi_rows=oi_rows, usable=usable)


def resolve_gex_scale_k(
    spy_spot: float,
    spx_spot: float,
    params: SPXCalibrationParams,
) -> float:
    """Effective GEX multiplier for this session."""
    if params.gex_scale_k is not None and params.gex_scale_k > 0:
        return float(params.gex_scale_k)
    return theoretical_gex_scale(spy_spot, spx_spot)


def resolve_strike_scale(
    spy_spot: float,
    spx_spot: float,
    params: SPXCalibrationParams,
) -> float:
    """Effective strike / flip multiplier."""
    if spx_spot > 0 and spy_spot > 0:
        return theoretical_strike_scale(spy_spot, spx_spot)
    return params.strike_scale


def spy_to_spx_proxy(
    snap: GEXSnapshot,
    params: SPXCalibrationParams,
    *,
    spx_spot: float | None = None,
) -> SPXGEXProxy:
    """Map one SPY GEX snapshot to an SPX estimate."""
    spy_spot = snap.spot
    if spx_spot is None:
        spx_spot = spy_spot * params.strike_scale
    k = resolve_gex_scale_k(spy_spot, spx_spot, params)
    strike_k = resolve_strike_scale(spy_spot, spx_spot, params)

    flip = (
        snap.flip_level * strike_k
        if np.isfinite(snap.flip_level)
        else float("nan")
    )
    above = bool(np.isfinite(flip) and spx_spot > flip)
    method = (
        "empirical_fixed_k"
        if params.gex_scale_k is not None
        else "theoretical_proxy"
    )

    return SPXGEXProxy(
        date=snap.date,
        spy_spot=spy_spot,
        spx_spot=spx_spot,
        net_gex_bn_per_1pct=snap.net_gex_bn_per_1pct * k,
        flip_level=flip,
        spot_above_flip=above,
        regime=snap.regime,
        gex_scale_k=k,
        method=method,
    )


def calibrate_paired_day(
    spy: GEXSnapshot,
    spx: GEXSnapshot,
    *,
    spx_usable: bool,
) -> PairedDayCalibration:
    """Compare one same-day SPY / SPX GEX snapshot pair."""
    strike_scale = theoretical_strike_scale(spy.spot, spx.spot)
    regime_match = spy.regime == spx.regime

    if (
        spx_usable
        and abs(spy.net_gex_bn_per_1pct) > 1e-6
        and np.sign(spy.net_gex_bn_per_1pct) == np.sign(spx.net_gex_bn_per_1pct)
    ):
        gex_k = float(spx.net_gex_bn_per_1pct / spy.net_gex_bn_per_1pct)
    else:
        gex_k = theoretical_gex_scale(spy.spot, spx.spot)

    flip_scale: float | None = None
    if np.isfinite(spy.flip_level) and np.isfinite(spx.flip_level) and spy.flip_level != 0:
        flip_scale = float(spx.flip_level / spy.flip_level)

    return PairedDayCalibration(
        date=spy.date,
        spy_spot=spy.spot,
        spx_spot=spx.spot,
        strike_scale=strike_scale,
        gex_scale_k=gex_k,
        flip_scale=flip_scale,
        regime_match=regime_match,
        spx_usable=spx_usable,
        spy_net_gex_bn=spy.net_gex_bn_per_1pct,
        spx_net_gex_bn=spx.net_gex_bn_per_1pct,
    )


def aggregate_paired_calibration(
    pairs: list[PairedDayCalibration],
) -> SPXCalibrationParams:
    """Collapse paired days into persisted calibration params."""
    if not pairs:
        return default_params()

    usable = [p for p in pairs if p.spx_usable]
    if usable:
        ks = [p.gex_scale_k for p in usable if np.isfinite(p.gex_scale_k) and p.gex_scale_k > 0]
        gex_k = float(np.median(ks)) if ks else None
        method = "empirical_median"
    else:
        gex_k = None
        method = "theoretical_proxy"

    strike_scales = [p.strike_scale for p in pairs if np.isfinite(p.strike_scale)]
    strike_scale = float(np.median(strike_scales)) if strike_scales else DEFAULT_STRIKE_SCALE

    return SPXCalibrationParams(
        gex_scale_k=gex_k,
        strike_scale=strike_scale,
        n_paired_days=len(pairs),
        paired_dates=tuple(p.date for p in pairs),
        method=method,
    )


def list_paired_snapshot_dates(
    spy_symbol: str = DEFAULT_SPY_SYMBOL,
    spx_symbol: str = DEFAULT_SPX_SYMBOL,
) -> list[str]:
    """Dates where both SPY and ^SPX chains exist on disk."""
    from quant_lab.data.storage import list_option_snapshots

    spy_dates = set(list_option_snapshots(spy_symbol))
    spx_dates = set(list_option_snapshots(spx_symbol))
    return sorted(spy_dates & spx_dates)


def calibration_config_path(path: Path | None = None) -> Path:
    return path or (settings.paths.project_root / "config" / "spx_spy_calibration.yaml")


def default_params() -> SPXCalibrationParams:
    return SPXCalibrationParams(gex_scale_k=None, strike_scale=DEFAULT_STRIKE_SCALE)


def load_calibration_params(path: Path | None = None) -> SPXCalibrationParams:
    """Load YAML calibration; fall back to theoretical proxy defaults."""
    cfg_path = calibration_config_path(path)
    if not cfg_path.exists():
        return default_params()
    with cfg_path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    gex_k = raw.get("gex_scale_k")
    if gex_k is not None:
        gex_k = float(gex_k)
    paired = raw.get("paired_dates") or []
    return SPXCalibrationParams(
        gex_scale_k=gex_k,
        strike_scale=float(raw.get("strike_scale", DEFAULT_STRIKE_SCALE)),
        min_spx_oi_rows=int(raw.get("min_spx_oi_rows", DEFAULT_MIN_SPX_OI_ROWS)),
        n_paired_days=int(raw.get("n_paired_days", len(paired))),
        paired_dates=tuple(str(d) for d in paired),
        method=str(raw.get("method", "theoretical_proxy")),
    )


def save_calibration_params(
    params: SPXCalibrationParams,
    path: Path | None = None,
    *,
    notes: str | None = None,
) -> Path:
    """Write calibration params to YAML."""
    cfg_path = calibration_config_path(path)
    payload: dict[str, Any] = {
        "gex_scale_k": params.gex_scale_k,
        "strike_scale": params.strike_scale,
        "min_spx_oi_rows": params.min_spx_oi_rows,
        "method": params.method,
        "n_paired_days": params.n_paired_days,
        "paired_dates": list(params.paired_dates),
    }
    if notes:
        payload["notes"] = notes
    with cfg_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)
    return cfg_path
