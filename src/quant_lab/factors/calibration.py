"""GEX calibration helpers.

Compares our GEX output against reference values from public / free sources:

- SpotGamma free blog narratives (direction-only)
- FlashAlpha free API (live magnitude + flip, optional ``FLASHALPHA_API_KEY``)
- Unusual Whales worked examples (single-contract sanity)

We support two calibration modes:

1. **Direction-only** — reference says ``regime: short_gamma`` and
   ``spot_below_flip: true``; we check sign / ordering without needing
   an exact dollar magnitude (useful when only narrative is public).

2. **Magnitude** — reference includes ``net_gex_bn_per_1pct``; we require
   agreement within ``tolerance_pct`` (default 30%, per ROADMAP Phase 1).

Reference files:

- ``config/spotgamma_reference.yaml`` — SpotGamma public narratives
- ``config/free_gex_reference.yaml`` — other free providers (FlashAlpha archive, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from quant_lab.config import settings
from quant_lab.factors.gex import (
    DEFAULT_DIVIDEND_YIELD,
    DEFAULT_RISK_FREE_RATE,
    add_bs_gamma_column,
    call_wall,
    compute_dealer_gamma_exposure,
    gamma_flip_level,
    net_gex_bn_per_1pct,
    put_wall,
    total_net_gex,
)


@dataclass(frozen=True)
class GEXSnapshot:
    """Our computed positioning metrics for one EoD session."""

    date: str
    spot: float
    net_gex_dollars_per_dollar: float
    net_gex_bn_per_1pct: float
    flip_level: float
    spot_above_flip: bool
    call_wall_strike: float
    put_wall_strike: float
    regime: str  # "long_gamma" | "short_gamma"


@dataclass(frozen=True)
class CalibrationCheck:
    date: str
    passed: bool
    messages: tuple[str, ...]


def compute_gex_snapshot(
    chain: pd.DataFrame,
    *,
    spot: float,
    asof_date: str,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> GEXSnapshot:
    """Full GEX snapshot for calibration / daily reporting."""
    with_gamma = add_bs_gamma_column(chain, spot=spot, r=r, q=q)
    per_strike = compute_dealer_gamma_exposure(with_gamma, spot=spot)
    net = total_net_gex(per_strike)
    flip = gamma_flip_level(with_gamma, spot=spot, r=r, q=q)
    above_flip = bool(np.isfinite(flip) and spot > flip)
    regime = "long_gamma" if net > 0 else "short_gamma"
    return GEXSnapshot(
        date=asof_date,
        spot=spot,
        net_gex_dollars_per_dollar=net,
        net_gex_bn_per_1pct=net_gex_bn_per_1pct(net),
        flip_level=float(flip) if np.isfinite(flip) else float("nan"),
        spot_above_flip=above_flip,
        call_wall_strike=call_wall(per_strike),
        put_wall_strike=put_wall(per_strike),
        regime=regime,
    )


def load_reference(path: Path | None = None) -> list[dict[str, Any]]:
    """Load YAML reference entries from one file."""
    ref_path = path or (settings.paths.project_root / "config" / "spotgamma_reference.yaml")
    if not ref_path.exists():
        raise FileNotFoundError(f"reference file not found: {ref_path}")
    with ref_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return list(raw.get("references", []))


def load_all_references(
    *paths: Path | None,
) -> list[dict[str, Any]]:
    """Load and merge reference entries from multiple YAML files."""
    if not paths:
        root = settings.paths.project_root / "config"
        paths = (
            root / "spotgamma_reference.yaml",
            root / "free_gex_reference.yaml",
        )
    merged: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for path in paths:
        if path is None or not path.exists():
            continue
        for ref in load_reference(path):
            key = str(ref.get("date", ""))
            if not key or key in seen_dates:
                continue
            seen_dates.add(key)
            merged.append(ref)
    return merged


def check_against_reference(
    snap: GEXSnapshot,
    ref: dict[str, Any],
    *,
    tolerance_pct: float = 0.30,
) -> CalibrationCheck:
    """Compare one snapshot to one reference dict."""
    messages: list[str] = []
    passed = True

    if ref.get("regime"):
        expected = str(ref["regime"])
        ok = snap.regime == expected
        passed &= ok
        messages.append(
            f"regime: ours={snap.regime} ref={expected} {'OK' if ok else 'FAIL'}"
        )

    if ref.get("spot_below_flip") is True:
        ok = not snap.spot_above_flip and np.isfinite(snap.flip_level)
        passed &= ok
        messages.append(
            f"spot_below_flip: spot={snap.spot:.2f} flip={snap.flip_level:.2f} "
            f"{'OK' if ok else 'FAIL'}"
        )
    if ref.get("spot_above_flip") is True:
        ok = snap.spot_above_flip
        passed &= ok
        messages.append(
            f"spot_above_flip: spot={snap.spot:.2f} flip={snap.flip_level:.2f} "
            f"{'OK' if ok else 'FAIL'}"
        )

    ref_mag = ref.get("net_gex_bn_per_1pct")
    if ref_mag is not None:
        ref_mag = float(ref_mag)
        if ref_mag == 0:
            ok = abs(snap.net_gex_bn_per_1pct) < 0.01
        else:
            ratio = snap.net_gex_bn_per_1pct / ref_mag
            ok = (1 - tolerance_pct) <= ratio <= (1 + tolerance_pct)
        passed &= ok
        messages.append(
            f"net_gex_bn_per_1pct: ours={snap.net_gex_bn_per_1pct:+.2f} "
            f"ref={ref_mag:+.2f} {'OK' if ok else 'FAIL'}"
        )

    ref_flip = ref.get("flip_level")
    if ref_flip is not None and np.isfinite(snap.flip_level):
        ref_flip = float(ref_flip)
        err = abs(snap.flip_level - ref_flip) / ref_flip
        ok = err <= tolerance_pct
        passed &= ok
        messages.append(
            f"flip_level: ours={snap.flip_level:.2f} ref={ref_flip:.2f} "
            f"err={err:.1%} {'OK' if ok else 'FAIL'}"
        )

    return CalibrationCheck(date=snap.date, passed=passed, messages=tuple(messages))


def check_against_external_gex(
    snap: GEXSnapshot,
    *,
    external_regime: str,
    external_net_gex_bn_per_1pct: float,
    external_flip: float,
    external_spot: float,
    provider: str,
    tolerance_pct: float = 0.30,
) -> CalibrationCheck:
    """Compare our snapshot to a live external GEX vendor (e.g. FlashAlpha)."""
    messages: list[str] = []
    passed = True

    ok_regime = snap.regime == external_regime
    passed &= ok_regime
    messages.append(
        f"regime ({provider}): ours={snap.regime} ext={external_regime} "
        f"{'OK' if ok_regime else 'FAIL'}"
    )

    if external_net_gex_bn_per_1pct == 0:
        ok_mag = abs(snap.net_gex_bn_per_1pct) < 0.01
    else:
        ratio = snap.net_gex_bn_per_1pct / external_net_gex_bn_per_1pct
        ok_mag = (1 - tolerance_pct) <= ratio <= (1 + tolerance_pct)
    passed &= ok_mag
    messages.append(
        f"net_gex_bn_per_1pct ({provider}): ours={snap.net_gex_bn_per_1pct:+.2f} "
        f"ext={external_net_gex_bn_per_1pct:+.2f} {'OK' if ok_mag else 'FAIL'}"
    )

    if np.isfinite(snap.flip_level) and np.isfinite(external_flip) and external_flip != 0:
        err = abs(snap.flip_level - external_flip) / external_flip
        ok_flip = err <= tolerance_pct
        passed &= ok_flip
        messages.append(
            f"flip_level ({provider}): ours={snap.flip_level:.2f} ext={external_flip:.2f} "
            f"err={err:.1%} {'OK' if ok_flip else 'FAIL'}"
        )

    spot_err = abs(snap.spot - external_spot) / external_spot if external_spot else float("inf")
    ok_spot = spot_err <= 0.02
    messages.append(
        f"spot ({provider}): ours={snap.spot:.2f} ext={external_spot:.2f} "
        f"err={spot_err:.1%} {'OK' if ok_spot else 'WARN (EoD vs live)'}"
    )

    return CalibrationCheck(date=snap.date, passed=passed, messages=tuple(messages))
