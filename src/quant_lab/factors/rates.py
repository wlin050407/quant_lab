"""Risk-free rate and dividend yield for GEX / pin greek inputs.

No network I/O. Resolution order:

1. Environment overrides (``QUANT_LAB_RISK_FREE_RATE``, per-symbol dividend envs).
2. Optional daily rate parquet under ``data/processed/`` (SOFR or similar).
3. ``config/settings.yaml`` → ``positioning`` section.

Index options (SPX / ^SPX) use **Black-76**; ETF underlyings (SPY) use **Merton BS**.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from quant_lab.config import env_var, settings

GexModel = Literal["black76", "bs"]


@dataclass(frozen=True)
class GexInputs:
    """Resolved rate inputs and pricing model for one underlying."""

    symbol: str
    r: float
    q: float
    model: GexModel
    r_source: str
    q_source: str


def normalize_underlying_symbol(symbol: str) -> str:
    """Canonical key for settings lookup (``SPX``, ``SPY``, ``QQQ``)."""
    s = symbol.strip().upper().replace("^", "")
    if s in ("SPXW", "GSPC"):
        return "SPX"
    return s


def is_index_underlying(symbol: str) -> bool:
    """Cash-settled index roots → Black-76."""
    return normalize_underlying_symbol(symbol) in ("SPX", "NDX", "RUT", "VIX")


def _parse_float_env(name: str) -> float | None:
    raw = env_var(name)
    if raw is None:
        return None
    try:
        val = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric, got {raw!r}") from exc
    if not np.isfinite(val):
        raise ValueError(f"{name} must be finite, got {val!r}")
    return val


def _dividend_from_env(key: str) -> float | None:
    sym = normalize_underlying_symbol(key)
    for env_name in (
        f"QUANT_LAB_DIVIDEND_YIELD_{sym}",
        "QUANT_LAB_DIVIDEND_YIELD",
    ):
        val = _parse_float_env(env_name)
        if val is not None:
            return val
    return None


def _load_rate_series_parquet(path: Path | None, asof: date | None) -> float | None:
    if path is None or asof is None or not path.is_file():
        return None
    df = pd.read_parquet(path)
    if df.empty or "rate" not in df.columns:
        return None
    if "date" not in df.columns:
        return None
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"]).dt.date
    past = work[work["date"] <= asof]
    if past.empty:
        return None
    rate = float(past.sort_values("date").iloc[-1]["rate"])
    return rate if np.isfinite(rate) else None


def resolve_gex_inputs(
    symbol: str,
    *,
    asof: date | None = None,
) -> GexInputs:
    """Resolve ``r``, ``q``, and BS vs Black-76 for dealer GEX on ``symbol``."""
    pos = settings.positioning
    key = normalize_underlying_symbol(symbol)

    r_source = "yaml_default"
    r = float(pos.risk_free_rate)
    env_r = _parse_float_env("QUANT_LAB_RISK_FREE_RATE")
    if env_r is not None:
        r, r_source = env_r, "env"
    else:
        series_path = pos.risk_free_rate_series
        if series_path is not None:
            loaded = _load_rate_series_parquet(series_path, asof)
            if loaded is not None:
                r, r_source = loaded, "series"

    q_source = "yaml_default"
    q = float(pos.dividend_yield.get(key, pos.dividend_yield.get("default", 0.013)))
    env_q = _dividend_from_env(key)
    if env_q is not None:
        q, q_source = env_q, "env"

    if is_index_underlying(key):
        model: GexModel = "black76"
    else:
        model = "bs"

    return GexInputs(
        symbol=key,
        r=r,
        q=q,
        model=model,
        r_source=r_source,
        q_source=q_source,
    )
