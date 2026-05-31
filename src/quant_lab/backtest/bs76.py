"""Black-76 / generalized BS European option pricing for EoD simulation."""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm

DEFAULT_RISK_FREE_RATE = 0.05
DEFAULT_DIVIDEND_YIELD = 0.013
TRADING_DAYS_PER_YEAR = 365


def _d1_d2(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    *,
    r: float,
    q: float,
) -> tuple[float, float]:
    if spot <= 0 or strike <= 0 or time_to_expiry <= 0 or volatility <= 0:
        return float("nan"), float("nan")
    vol_sqrt_t = volatility * math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + (r - q + 0.5 * volatility**2) * time_to_expiry) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


def bs_call_price(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    *,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> float:
    """Generalized BS call price (continuous yield ``q``)."""
    d1, d2 = _d1_d2(spot, strike, time_to_expiry, volatility, r=r, q=q)
    if not np.isfinite(d1):
        return float("nan")
    return float(
        spot * math.exp(-q * time_to_expiry) * norm.cdf(d1)
        - strike * math.exp(-r * time_to_expiry) * norm.cdf(d2)
    )


def bs_put_price(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    *,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> float:
    """Generalized BS put price (continuous yield ``q``)."""
    d1, d2 = _d1_d2(spot, strike, time_to_expiry, volatility, r=r, q=q)
    if not np.isfinite(d1):
        return float("nan")
    return float(
        strike * math.exp(-r * time_to_expiry) * norm.cdf(-d2)
        - spot * math.exp(-q * time_to_expiry) * norm.cdf(-d1)
    )


def intrinsic_value(spot: float, strike: float, right: str) -> float:
    """Expiry intrinsic value per share."""
    if right == "C":
        return float(max(spot - strike, 0.0))
    if right == "P":
        return float(max(strike - spot, 0.0))
    raise ValueError(f"right must be 'C' or 'P', got {right!r}")


def mark_price(
    spot: float,
    strike: float,
    right: str,
    time_to_expiry: float,
    volatility: float,
    *,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> float:
    """BS mark; falls back to intrinsic when ``T`` is negligible."""
    if time_to_expiry <= 1e-6:
        return intrinsic_value(spot, strike, right)
    if right == "C":
        return bs_call_price(spot, strike, time_to_expiry, volatility, r=r, q=q)
    if right == "P":
        return bs_put_price(spot, strike, time_to_expiry, volatility, r=r, q=q)
    raise ValueError(f"right must be 'C' or 'P', got {right!r}")
