"""Implied volatility from European BS mid prices (Options Value — no vendor Greeks)."""

from __future__ import annotations

import numpy as np

from quant_lab.backtest.bs76 import bs_call_price, bs_put_price

DEFAULT_RISK_FREE_RATE = 0.05
DEFAULT_DIVIDEND_YIELD = 0.013


def implied_volatility_from_mid(
    spot: float,
    strike: float,
    right: str,
    mid: float,
    time_to_expiry: float,
    *,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
    vol_lo: float = 0.01,
    vol_hi: float = 5.0,
    max_iter: int = 60,
) -> float:
    """Bisection IV solver; returns NaN when no valid root."""
    if (
        not np.isfinite(spot)
        or not np.isfinite(strike)
        or spot <= 0
        or strike <= 0
        or not np.isfinite(mid)
        or mid <= 0
        or time_to_expiry <= 0
    ):
        return float("nan")

    right_u = right.upper()
    if right_u in ("CALL", "C"):
        pricer = bs_call_price
    elif right_u in ("PUT", "P"):
        pricer = bs_put_price
    else:
        raise ValueError(f"right must be C/P, got {right!r}")

    lo, hi = vol_lo, vol_hi
    price_lo = pricer(spot, strike, time_to_expiry, lo, r=r, q=q)
    price_hi = pricer(spot, strike, time_to_expiry, hi, r=r, q=q)
    if not np.isfinite(price_lo) or not np.isfinite(price_hi):
        return float("nan")
    if mid <= price_lo:
        return lo
    if mid >= price_hi:
        return hi

    for _ in range(max_iter):
        mid_vol = 0.5 * (lo + hi)
        price = pricer(spot, strike, time_to_expiry, mid_vol, r=r, q=q)
        if not np.isfinite(price):
            return float("nan")
        if abs(price - mid) < 1e-4:
            return mid_vol
        if price < mid:
            lo = mid_vol
        else:
            hi = mid_vol
    return 0.5 * (lo + hi)
