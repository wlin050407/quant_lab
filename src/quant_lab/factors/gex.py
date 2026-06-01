"""Dealer Gamma Exposure (GEX) and gamma flip level.

`GEX` is the dollar P&L sensitivity of the dealer book to a $1 move in the
underlying, aggregated across the option chain. It's the single most useful
positioning factor for 0DTE research:

- Net GEX > 0 → dealer is long gamma → mechanical hedging *suppresses* spot moves
  (spot rises → dealer sells; spot falls → dealer buys; both dampen). Regime
  tends toward mean-reversion and low realized vol.
- Net GEX < 0 → dealer is short gamma → mechanical hedging *amplifies* spot moves
  (spot rises → dealer buys more; spot falls → dealer sells more). Regime tends
  toward trends and high realized vol.

The crossover spot price is the **gamma flip level**, probably the most-quoted
single number in 0DTE strategy commentary.

## Dealer sign convention (READ THIS BEFORE USING)

We use the **SpotGamma convention**:

    dealer is LONG calls  (+1)
    dealer is SHORT puts  (-1)

This reflects the stylized flow assumption:
- Retail systematically sells calls (covered calls, wheel strategies).
- Institutions systematically buy puts (protective hedges).
- Dealers absorb the other side of both, so they end up long calls / short puts.

This is a **default assumption**, not a fact. In the 0DTE era retail has also
been a heavy *buyer* of OTM calls (lottery / momentum trades), which can flip
the sign at the call wings on specific days. If your factor predicts the wrong
direction in backtest, the very first thing to check is whether this default
holds for your regime — pass a custom `dealer_sign` to
`compute_dealer_gamma_exposure` to flip it.

## Math

Single-contract gamma uses the Generalized Black-Scholes formula with a
continuous dividend yield `q` (handles both SPY ETF dividends and the SPX cash
dividend stream):

    d1    = (ln(S/K) + (r - q + σ²/2) · T) / (σ · √T)
    gamma = exp(-q·T) · φ(d1) / (S · σ · √T)

where φ is the standard normal PDF. Call gamma and put gamma are equal under
this formula (a consequence of put-call parity).

Aggregated dealer exposure per `$1` move in spot:

    contract_gex   = gamma · OI · multiplier · spot²
    net_gex_dollars = Σ (contract_gex_i · dealer_sign_i)

with `multiplier = 100` for SPY / SPX. Divide by 1e9 for the "billions per $1
move" headline number, or multiply by 0.01 for "dollars per 1% move".

## What this module does NOT do

- It does NOT pull risk-free rates or dividend yields from any data source.
  `r` and `q` are caller-supplied. Defaults are coarse (`r=0.05`, `q=0.013`);
  any production use should pull SOFR + the underlying's trailing yield.
- It does NOT handle the T=0 singularity. dte=0 contracts on an EoD snapshot
  have already expired, so we return NaN gamma for them. Research 0DTE behavior
  using dte=1 rows on the *prior* EoD snapshot, which is the actual 0DTE
  starting position from a tomorrow-morning trader's perspective.
- **VEX (vanna exposure)** shares the same BS pass and dealer-sign convention as
  GEX; see ``bs_vanna``, ``compute_dealer_vanna_exposure``, ``compute_vex_profile``.
- It does NOT compute charm or other higher-order Greeks beyond vanna.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping

import numpy as np
import pandas as pd
from scipy.stats import norm

from quant_lab.factors.rates import GexModel, resolve_gex_inputs

DEFAULT_RISK_FREE_RATE = 0.05
DEFAULT_DIVIDEND_YIELD = 0.013
DEFAULT_CONTRACT_MULTIPLIER = 100
DEFAULT_DEALER_SIGN: Mapping[str, int] = {"C": 1, "P": -1}
TRADING_DAYS_PER_YEAR = 365
TRADING_HOURS_PER_DAY = 6.5


def effective_time_to_expiry_years(chain: pd.DataFrame) -> np.ndarray:
    """Years-to-expiry per chain row, aligned with ``add_bs_gamma_column``.

    Prefers ``time_to_expiry_years`` (intraday ThetaData). Falls back to
    ``dte / 365``. EoD ``dte=0`` rows use ~1 trading hour so 0DTE gamma is
    finite on same-day snapshots.
    """
    if "time_to_expiry_years" in chain.columns:
        t_years = pd.to_numeric(chain["time_to_expiry_years"], errors="coerce").astype("float64")
        dte = chain["dte"].astype("float64")
        mask0 = (dte == 0) & (~np.isfinite(t_years) | (t_years <= 0))
        return t_years.mask(mask0, 1.0 / (TRADING_DAYS_PER_YEAR * TRADING_HOURS_PER_DAY)).to_numpy()
    t_years = chain["dte"].astype("float64") / TRADING_DAYS_PER_YEAR
    mask0 = (chain["dte"].astype("float64") == 0) & (t_years <= 0)
    return t_years.mask(mask0, 1.0 / (TRADING_DAYS_PER_YEAR * TRADING_HOURS_PER_DAY)).to_numpy()


def bs_gamma(
    spot: float | np.ndarray,
    strike: float | np.ndarray,
    time_to_expiry: float | np.ndarray,
    volatility: float | np.ndarray,
    *,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> float | np.ndarray:
    """Generalized Black-Scholes gamma (with continuous dividend yield).

    Same formula for calls and puts. Vectorized over numpy-broadcastable inputs.

    Args:
        spot: underlying spot price (S, $)
        strike: option strike (K, $)
        time_to_expiry: years to expiry (T). Must be > 0. Calendar-day basis
            (365), matching the IV convention reported by every standard
            options data feed including yfinance and the Philipp Dubach dataset.
        volatility: annualized implied volatility (σ, decimal). Must be > 0.
        r: continuously-compounded risk-free rate.
        q: continuously-compounded dividend yield. SPY ≈ 1.3%, SPX ≈ 1.3-1.5%.

    Returns:
        Gamma (1/$): change in delta per $1 spot move. Scalar in, scalar out;
        array in, array out.

    NaN propagates: any non-finite input row returns NaN, which is the right
    thing on EoD data where dte=0 / zero IV / missing strike happens routinely.
    """
    s = np.asarray(spot, dtype="float64")
    k = np.asarray(strike, dtype="float64")
    t = np.asarray(time_to_expiry, dtype="float64")
    sigma = np.asarray(volatility, dtype="float64")

    with np.errstate(divide="ignore", invalid="ignore"):
        valid = (s > 0) & (k > 0) & (t > 0) & (sigma > 0)
        d1 = np.where(
            valid,
            (np.log(s / k) + (r - q + 0.5 * sigma**2) * t) / (sigma * np.sqrt(t)),
            np.nan,
        )
        gamma = np.where(
            valid,
            np.exp(-q * t) * norm.pdf(d1) / (s * sigma * np.sqrt(t)),
            np.nan,
        )

    if gamma.ndim == 0:
        return float(gamma)
    return gamma


def black76_gamma(
    spot: float | np.ndarray,
    strike: float | np.ndarray,
    time_to_expiry: float | np.ndarray,
    volatility: float | np.ndarray,
    *,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> float | np.ndarray:
    """Black-76 gamma (∂Δ/∂S) for options on equity-index forward.

    Forward ``F = S · exp((r−q)T)``. Uses the Black-76 ``d₁`` on ``F/K``, then
    chain-rule to spot. For cash-settled index 0DTE (SPX) per AGENTS.md / Phase 1.
    """
    s = np.asarray(spot, dtype="float64")
    k = np.asarray(strike, dtype="float64")
    t = np.asarray(time_to_expiry, dtype="float64")
    sigma = np.asarray(volatility, dtype="float64")

    with np.errstate(divide="ignore", invalid="ignore"):
        valid = (s > 0) & (k > 0) & (t > 0) & (sigma > 0)
        F = np.where(valid, s * np.exp((r - q) * t), np.nan)
        d1 = np.where(
            valid,
            (np.log(F / k) + 0.5 * sigma**2 * t) / (sigma * np.sqrt(t)),
            np.nan,
        )
        gamma_f = np.where(
            valid,
            np.exp(-r * t) * norm.pdf(d1) / (F * sigma * np.sqrt(t)),
            np.nan,
        )
        gamma = np.where(valid, gamma_f * np.exp((r - q) * t), np.nan)

    if gamma.ndim == 0:
        return float(gamma)
    return gamma


def contract_gamma_spot(
    spot: float | np.ndarray,
    strike: float | np.ndarray,
    time_to_expiry: float | np.ndarray,
    volatility: float | np.ndarray,
    *,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
    model: GexModel = "bs",
) -> float | np.ndarray:
    """Spot gamma for dealer GEX (BS or Black-76)."""
    if model == "black76":
        return black76_gamma(
            spot,
            strike,
            time_to_expiry,
            volatility,
            r=r,
            q=q,
        )
    return bs_gamma(spot, strike, time_to_expiry, volatility, r=r, q=q)


def resolve_gex_params(
    *,
    symbol: str | None,
    asof: date | None = None,
    r: float | None = None,
    q: float | None = None,
    model: GexModel | None = None,
) -> tuple[float, float, GexModel]:
    """Merge explicit ``r``/``q``/``model`` with ``settings.yaml`` + env for ``symbol``."""
    if symbol is not None:
        inp = resolve_gex_inputs(symbol, asof=asof)
        return (
            inp.r if r is None else r,
            inp.q if q is None else q,
            inp.model if model is None else model,
        )
    return (
        r if r is not None else DEFAULT_RISK_FREE_RATE,
        q if q is not None else DEFAULT_DIVIDEND_YIELD,
        model if model is not None else "bs",
    )


def chain_symbol(chain: pd.DataFrame, fallback: str | None = None) -> str | None:
    """Underlying symbol from chain rows if present."""
    if "symbol" in chain.columns and not chain.empty:
        raw = str(chain["symbol"].iloc[0])
        return raw
    return fallback


def add_bs_gamma_column(
    chain: pd.DataFrame,
    spot: float,
    *,
    symbol: str | None = None,
    asof: date | None = None,
    r: float | None = None,
    q: float | None = None,
    model: GexModel | None = None,
    output_col: str = "bs_gamma",
) -> pd.DataFrame:
    """Return a copy of `chain` with an added gamma column (BS or Black-76).

    When ``symbol`` is set (or present on the chain), ``r``/``q``/``model`` default
    from ``factors/rates.resolve_gex_inputs`` (SPX → Black-76).

    The chain must follow `quant_lab.data.base.REQUIRED_OPTION_COLUMNS`:
    `strike`, `dte`, `implied_volatility` are the inputs consumed here. Rows
    where any of those is non-positive (including dte=0, the already-expired
    EoD contracts) get NaN gamma rather than +inf — see module docstring.

    Args:
        chain: a single-snapshot option chain.
        spot: snapshot spot price.
        symbol: underlying for rate/model resolution (e.g. ``^SPX``, ``SPY``).
        asof: session date for optional SOFR series lookup.
        r, q, model: overrides; omitted → resolved from config/env.
        output_col: column name (default ``bs_gamma`` for downstream GEX agg).

    Returns:
        New DataFrame with the same rows and one extra column.
    """
    for col in ("strike", "dte", "implied_volatility"):
        if col not in chain.columns:
            raise ValueError(f"chain is missing required column {col!r}")

    sym = symbol or chain_symbol(chain)
    r_eff, q_eff, model_eff = resolve_gex_params(
        symbol=sym, asof=asof, r=r, q=q, model=model
    )

    out = chain.copy()
    t_years = effective_time_to_expiry_years(out)
    out[output_col] = contract_gamma_spot(
        spot=spot,
        strike=out["strike"].to_numpy(dtype="float64"),
        time_to_expiry=t_years,
        volatility=out["implied_volatility"].to_numpy(dtype="float64"),
        r=r_eff,
        q=q_eff,
        model=model_eff,
    )
    return out


def bs_vanna(
    spot: float | np.ndarray,
    strike: float | np.ndarray,
    time_to_expiry: float | np.ndarray,
    volatility: float | np.ndarray,
    *,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> float | np.ndarray:
    """Generalized Black-Scholes vanna (∂Δ/∂σ).

    Same formula for calls and puts (put-call parity). ``σ`` is decimal annualized
    IV; the returned value is sensitivity of delta to a +1.0 absolute vol move.
    For a 1% IV move, multiply by ``0.01``.

    Args:
        spot, strike, time_to_expiry, volatility: BS inputs (see ``bs_gamma``).
        r, q: continuously-compounded rate and dividend yield.

    Returns:
        Vanna (1/vol-unit): ∂Δ/∂σ. NaN on degenerate rows.
    """
    s = np.asarray(spot, dtype="float64")
    k = np.asarray(strike, dtype="float64")
    t = np.asarray(time_to_expiry, dtype="float64")
    sigma = np.asarray(volatility, dtype="float64")

    with np.errstate(divide="ignore", invalid="ignore"):
        valid = (s > 0) & (k > 0) & (t > 0) & (sigma > 0)
        d1 = np.where(
            valid,
            (np.log(s / k) + (r - q + 0.5 * sigma**2) * t) / (sigma * np.sqrt(t)),
            np.nan,
        )
        d2 = np.where(valid, d1 - sigma * np.sqrt(t), np.nan)
        vanna = np.where(
            valid,
            -np.exp(-q * t) * norm.pdf(d1) * d2 / sigma,
            np.nan,
        )

    if vanna.ndim == 0:
        return float(vanna)
    return vanna


def black76_vanna(
    spot: float | np.ndarray,
    strike: float | np.ndarray,
    time_to_expiry: float | np.ndarray,
    volatility: float | np.ndarray,
    *,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> float | np.ndarray:
    """Black-76 vanna (∂Δ/∂σ) mapped to spot delta."""
    s = np.asarray(spot, dtype="float64")
    k = np.asarray(strike, dtype="float64")
    t = np.asarray(time_to_expiry, dtype="float64")
    sigma = np.asarray(volatility, dtype="float64")

    with np.errstate(divide="ignore", invalid="ignore"):
        valid = (s > 0) & (k > 0) & (t > 0) & (sigma > 0)
        F = np.where(valid, s * np.exp((r - q) * t), np.nan)
        d1 = np.where(
            valid,
            (np.log(F / k) + 0.5 * sigma**2 * t) / (sigma * np.sqrt(t)),
            np.nan,
        )
        d2 = np.where(valid, d1 - sigma * np.sqrt(t), np.nan)
        vanna_f = np.where(
            valid,
            -np.exp(-r * t) * norm.pdf(d1) * d2 / sigma,
            np.nan,
        )
        vanna = np.where(valid, vanna_f * np.exp((r - q) * t), np.nan)

    if vanna.ndim == 0:
        return float(vanna)
    return vanna


def contract_vanna_spot(
    spot: float | np.ndarray,
    strike: float | np.ndarray,
    time_to_expiry: float | np.ndarray,
    volatility: float | np.ndarray,
    *,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
    model: GexModel = "bs",
) -> float | np.ndarray:
    """Spot vanna for dealer VEX."""
    if model == "black76":
        return black76_vanna(
            spot, strike, time_to_expiry, volatility, r=r, q=q
        )
    return bs_vanna(spot, strike, time_to_expiry, volatility, r=r, q=q)


def add_bs_vanna_column(
    chain: pd.DataFrame,
    spot: float,
    *,
    symbol: str | None = None,
    asof: date | None = None,
    r: float | None = None,
    q: float | None = None,
    model: GexModel | None = None,
    output_col: str = "bs_vanna",
) -> pd.DataFrame:
    """Return a copy of ``chain`` with an added vanna column (BS or Black-76)."""
    for col in ("strike", "dte", "implied_volatility"):
        if col not in chain.columns:
            raise ValueError(f"chain is missing required column {col!r}")

    sym = symbol or chain_symbol(chain)
    r_eff, q_eff, model_eff = resolve_gex_params(
        symbol=sym, asof=asof, r=r, q=q, model=model
    )

    out = chain.copy()
    t_years = effective_time_to_expiry_years(out)
    out[output_col] = contract_vanna_spot(
        spot=spot,
        strike=out["strike"].to_numpy(dtype="float64"),
        time_to_expiry=t_years,
        volatility=out["implied_volatility"].to_numpy(dtype="float64"),
        r=r_eff,
        q=q_eff,
        model=model_eff,
    )
    return out


def compute_dealer_gamma_exposure(
    chain: pd.DataFrame,
    spot: float,
    *,
    gamma_col: str = "bs_gamma",
    dealer_sign: Mapping[str, int] = DEFAULT_DEALER_SIGN,
    multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
) -> pd.DataFrame:
    """Aggregate signed dealer gamma exposure per strike.

    Per-row contract GEX (dollars per $1 spot move):

        contract_gex = gamma · OI · multiplier · spot²
        signed_gex   = contract_gex · dealer_sign[right]

    Aggregated by strike and split call/put for transparency:

        | strike | call_oi | put_oi | call_gex | put_gex | net_gex | total_oi |

    Where `call_gex` and `put_gex` already carry their respective dealer signs,
    so `net_gex = call_gex + put_gex` directly.

    Args:
        chain: option chain with at least `strike`, `right`, `open_interest`,
            and the `gamma_col` (default `bs_gamma`) column. Run
            `add_bs_gamma_column` first if needed.
        spot: snapshot spot price (used in the `spot²` term).
        gamma_col: name of the gamma column to use. `bs_gamma` for our BS
            implementation, `gamma` for the Philipp Dubach dataset's
            pre-computed Greeks.
        dealer_sign: mapping from right ('C'/'P') to signed integer. Default
            uses the SpotGamma convention (long calls, short puts). Override
            this if you have evidence your regime flipped.
        multiplier: contract size. 100 for both SPY and SPX.

    Returns:
        DataFrame indexed by strike (ascending), columns as documented above.
        Empty input → empty DataFrame with the right column schema.
    """
    required = {"strike", "right", "open_interest", gamma_col}
    missing = required - set(chain.columns)
    if missing:
        raise ValueError(f"chain is missing required columns: {sorted(missing)}")

    if not np.isfinite(spot) or spot <= 0:
        raise ValueError(f"spot must be positive and finite, got {spot!r}")

    empty_schema = pd.DataFrame(
        columns=["call_oi", "put_oi", "call_gex", "put_gex", "net_gex", "total_oi"]
    )
    empty_schema.index.name = "strike"
    if chain.empty:
        return empty_schema

    work = chain[["strike", "right", "open_interest", gamma_col]].copy()
    work = work.dropna(subset=[gamma_col])
    if work.empty:
        return empty_schema

    work["contract_gex"] = (
        work[gamma_col].to_numpy(dtype="float64")
        * work["open_interest"].to_numpy(dtype="float64")
        * multiplier
        * spot
        * spot
    )

    sign_series = work["right"].map(dict(dealer_sign)).astype("float64")
    if sign_series.isna().any():
        bad = work.loc[sign_series.isna(), "right"].unique().tolist()
        raise ValueError(f"unrecognized right values not in dealer_sign: {bad}")
    work["signed_gex"] = work["contract_gex"] * sign_series

    work["open_interest"] = work["open_interest"].astype("float64")
    pivot = work.pivot_table(
        index="strike",
        columns="right",
        values=["open_interest", "signed_gex"],
        aggfunc="sum",
        fill_value=0.0,
    )

    zeros = pd.Series(0.0, index=pivot.index)
    call_oi = pivot.get(("open_interest", "C"), zeros)
    put_oi = pivot.get(("open_interest", "P"), zeros)
    call_gex = pivot.get(("signed_gex", "C"), zeros)
    put_gex = pivot.get(("signed_gex", "P"), zeros)

    out = pd.DataFrame(
        {
            "call_oi": call_oi.round().astype("int64"),
            "put_oi": put_oi.round().astype("int64"),
            "call_gex": call_gex.astype("float64"),
            "put_gex": put_gex.astype("float64"),
        },
        index=pivot.index,
    )
    out["net_gex"] = out["call_gex"] + out["put_gex"]
    out["total_oi"] = out["call_oi"] + out["put_oi"]
    return out.sort_index()


def compute_dealer_vanna_exposure(
    chain: pd.DataFrame,
    spot: float,
    *,
    vanna_col: str = "bs_vanna",
    dealer_sign: Mapping[str, int] = DEFAULT_DEALER_SIGN,
    multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
) -> pd.DataFrame:
    """Aggregate signed dealer vanna exposure per strike.

    Per-row contract VEX (dollar delta hedge per **1% IV** move):

        contract_vex = vanna · 0.01 · OI · multiplier · spot
        signed_vex   = contract_vex · dealer_sign[right]

    Uses the same SpotGamma dealer-sign convention as GEX.
    """
    required = {"strike", "right", "open_interest", vanna_col}
    missing = required - set(chain.columns)
    if missing:
        raise ValueError(f"chain is missing required columns: {sorted(missing)}")

    if not np.isfinite(spot) or spot <= 0:
        raise ValueError(f"spot must be positive and finite, got {spot!r}")

    empty_schema = pd.DataFrame(
        columns=["call_oi", "put_oi", "call_vex", "put_vex", "net_vex", "total_oi"]
    )
    empty_schema.index.name = "strike"
    if chain.empty:
        return empty_schema

    work = chain[["strike", "right", "open_interest", vanna_col]].copy()
    work = work.dropna(subset=[vanna_col])
    if work.empty:
        return empty_schema

    work["contract_vex"] = (
        work[vanna_col].to_numpy(dtype="float64")
        * 0.01
        * work["open_interest"].to_numpy(dtype="float64")
        * multiplier
        * spot
    )

    sign_series = work["right"].map(dict(dealer_sign)).astype("float64")
    if sign_series.isna().any():
        bad = work.loc[sign_series.isna(), "right"].unique().tolist()
        raise ValueError(f"unrecognized right values not in dealer_sign: {bad}")
    work["signed_vex"] = work["contract_vex"] * sign_series

    work["open_interest"] = work["open_interest"].astype("float64")
    pivot = work.pivot_table(
        index="strike",
        columns="right",
        values=["open_interest", "signed_vex"],
        aggfunc="sum",
        fill_value=0.0,
    )

    zeros = pd.Series(0.0, index=pivot.index)
    call_oi = pivot.get(("open_interest", "C"), zeros)
    put_oi = pivot.get(("open_interest", "P"), zeros)
    call_vex = pivot.get(("signed_vex", "C"), zeros)
    put_vex = pivot.get(("signed_vex", "P"), zeros)

    out = pd.DataFrame(
        {
            "call_oi": call_oi.round().astype("int64"),
            "put_oi": put_oi.round().astype("int64"),
            "call_vex": call_vex.astype("float64"),
            "put_vex": put_vex.astype("float64"),
        },
        index=pivot.index,
    )
    out["net_vex"] = out["call_vex"] + out["put_vex"]
    out["total_oi"] = out["call_oi"] + out["put_oi"]
    return out.sort_index()


def total_net_gex(per_strike: pd.DataFrame) -> float:
    """Sum of `net_gex` across strikes. Convenience for headline numbers.

    Returns **dollar-gamma notional per $1 spot move** (internal convention):

        Σ sign × Γ × OI × 100 × S²

    SpotGamma / SqueezeMetrics headline numbers are **per 1% move in billions**;
    convert with `net_gex_bn_per_1pct()`.
    """
    if per_strike.empty:
        return 0.0
    return float(per_strike["net_gex"].sum())


def total_net_vex(per_strike: pd.DataFrame) -> float:
    """Sum of ``net_vex`` across strikes.

    Returns **signed dollar delta hedge flow per 1% IV move** (internal):

        Σ sign × vanna × 0.01 × OI × 100 × spot
    """
    if per_strike.empty:
        return 0.0
    return float(per_strike["net_vex"].sum())


def net_vex_bn_per_1pct(net_vex_dollars: float) -> float:
    """Convert internal net VEX to billions (headline scale)."""
    return float(net_vex_dollars / 1e9)


def net_gex_bn_per_1pct(net_gex_dollars_per_dollar: float) -> float:
    """Convert internal net GEX to SpotGamma-style billions per 1% move.

    SpotGamma defines GEX for a 1% underlying move as:

        0.01 × Σ sign × Γ × OI × 100 × S²

    Our `total_net_gex` omits the leading 0.01, so we multiply here and
    divide by 1e9 for billions.
    """
    return float(net_gex_dollars_per_dollar * 0.01 / 1e9)


def net_gex_at_strike(per_strike: pd.DataFrame, strike: float) -> float:
    """Signed net GEX at the listed strike nearest to ``strike``."""
    if per_strike.empty or not np.isfinite(strike):
        return float("nan")
    idx = per_strike.index.to_numpy(dtype="float64")
    nearest = float(idx[np.argmin(np.abs(idx - strike))])
    return float(per_strike.loc[nearest, "net_gex"])


def max_abs_net_gex_bn(per_strike: pd.DataFrame) -> float:
    """Largest ``|net_gex|`` on the book in Bn/1% units (pin gamma normalizer)."""
    if per_strike.empty or "net_gex" not in per_strike.columns:
        return float("nan")
    bn = per_strike["net_gex"].astype("float64").map(net_gex_bn_per_1pct)
    return float(bn.abs().max())


def uw_gamma_notional_per_1pct(
    gamma: float,
    open_interest: float,
    *,
    multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
) -> float:
    """Unusual Whales / flow-scanner shortcut for per-contract gamma impact.

    Documented in UW's GEX explainer as::

        contracts × 100 × gamma

    This is a **relative** notional (no × S² term) used for comparing trades
    on a chart — not the same number as SpotGamma aggregate GEX. We expose it
    for sanity-checking single-row magnitudes against published examples.
    """
    return float(gamma * open_interest * multiplier)


def call_wall(per_strike: pd.DataFrame) -> float:
    """Strike with the largest signed call-side dealer GEX (resistance magnet)."""
    if per_strike.empty or "call_gex" not in per_strike.columns:
        return float("nan")
    return float(per_strike["call_gex"].idxmax())


def put_wall(per_strike: pd.DataFrame) -> float:
    """Strike with the most negative signed put-side dealer GEX (support magnet)."""
    if per_strike.empty or "put_gex" not in per_strike.columns:
        return float("nan")
    return float(per_strike["put_gex"].idxmin())


def king_node(per_strike: pd.DataFrame) -> float:
    """Strike with the largest absolute net GEX (Skylit King Node).

    Uses ``|net_gex|`` regardless of sign — the session's structural gravity.
    """
    if per_strike.empty or "net_gex" not in per_strike.columns:
        return float("nan")
    return float(per_strike["net_gex"].abs().idxmax())


def strongest_floor(per_strike: pd.DataFrame, spot: float) -> float:
    """Largest-|net_gex| strike strictly below ``spot`` (support magnet)."""
    if per_strike.empty or not np.isfinite(spot):
        return float("nan")
    below = per_strike[per_strike.index.astype("float64") < spot]
    if below.empty:
        return float("nan")
    return float(below["net_gex"].abs().idxmax())


def strongest_ceiling(per_strike: pd.DataFrame, spot: float) -> float:
    """Largest-|net_gex| strike strictly above ``spot`` (resistance magnet)."""
    if per_strike.empty or not np.isfinite(spot):
        return float("nan")
    above = per_strike[per_strike.index.astype("float64") > spot]
    if above.empty:
        return float("nan")
    return float(above["net_gex"].abs().idxmax())


def filter_chain_by_dte(chain: pd.DataFrame, *, dte_max: int | None = None) -> pd.DataFrame:
    """Return chain rows with ``dte <= dte_max`` (inclusive)."""
    if dte_max is None:
        return chain.copy()
    if chain.empty:
        return chain.copy()
    if "dte" not in chain.columns:
        raise ValueError("dte_max filter requires a 'dte' column")
    return chain[chain["dte"] <= dte_max].copy()


@dataclass(frozen=True)
class GexProfile:
    """Headline GEX levels for one chain cohort (full chain or dte-filtered)."""

    net_gex: float
    flip_level: float
    call_wall: float
    put_wall: float
    king_node: float
    floor_strike: float
    ceiling_strike: float
    n_contracts: int


def compute_gex_profile(
    chain: pd.DataFrame,
    spot: float,
    *,
    symbol: str | None = None,
    asof: date | None = None,
    dte_max: int | None = None,
    r: float | None = None,
    q: float | None = None,
    model: GexModel | None = None,
    compute_flip: bool = True,
) -> GexProfile:
    """Compute net GEX, flip, walls, King, floor/ceiling for a chain cohort.

    Args:
        chain: single EoD option chain snapshot.
        spot: underlying spot at snapshot.
        symbol: underlying for ``r``/``q``/Black-76 vs BS (e.g. ``^SPX``).
        asof: session date for optional rate series.
        dte_max: if set, only include ``dte <= dte_max`` (e.g. 1 for next-day 0DTE).
        r, q, model: overrides; default from ``resolve_gex_inputs``.
        compute_flip: if False, skip flip (faster bulk builds).
    """
    work = filter_chain_by_dte(chain, dte_max=dte_max)
    if work.empty:
        return GexProfile(
            net_gex=0.0,
            flip_level=float("nan"),
            call_wall=float("nan"),
            put_wall=float("nan"),
            king_node=float("nan"),
            floor_strike=float("nan"),
            ceiling_strike=float("nan"),
            n_contracts=0,
        )

    sym = symbol or chain_symbol(chain)
    r_eff, q_eff, model_eff = resolve_gex_params(
        symbol=sym, asof=asof, r=r, q=q, model=model
    )

    with_gamma = add_bs_gamma_column(
        work, spot, symbol=sym, asof=asof, r=r_eff, q=q_eff, model=model_eff
    )
    per_strike = compute_dealer_gamma_exposure(with_gamma, spot)
    net = total_net_gex(per_strike)
    flip = (
        gamma_flip_level(
            work,
            spot,
            symbol=sym,
            asof=asof,
            r=r_eff,
            q=q_eff,
            model=model_eff,
        )
        if compute_flip
        else float("nan")
    )
    return GexProfile(
        net_gex=net,
        flip_level=float(flip),
        call_wall=call_wall(per_strike),
        put_wall=put_wall(per_strike),
        king_node=king_node(per_strike),
        floor_strike=strongest_floor(per_strike, spot),
        ceiling_strike=strongest_ceiling(per_strike, spot),
        n_contracts=len(work),
    )


def pct_dte_cohort_of_total(net_dte: float, net_total: float) -> float:
    """0DTE cohort GEX as percent of full-chain net GEX (FlashAlpha ``pct_of_total_gex``)."""
    if not np.isfinite(net_total) or abs(net_total) < 1e-9:
        return float("nan")
    return float(net_dte / net_total * 100.0)


def vanna_interpretation(net_vex: float) -> str:
    """FlashAlpha-style dealer hedging label from aggregate net VEX.

    Negative net VEX (typical for index books): vol crush → dealers buy delta;
    vol spike → dealers sell. Positive net VEX inverts the flow.
    """
    if not np.isfinite(net_vex):
        return "undetermined"
    if net_vex < 0:
        return "vol_down_dealers_buy"
    if net_vex > 0:
        return "vol_down_dealers_sell"
    return "neutral"


@dataclass(frozen=True)
class VexProfile:
    """Headline VEX levels for one chain cohort."""

    net_vex: float
    king_node: float
    call_wall: float
    put_wall: float
    n_contracts: int
    interpretation: str


def compute_vex_profile(
    chain: pd.DataFrame,
    spot: float,
    *,
    symbol: str | None = None,
    asof: date | None = None,
    dte_max: int | None = None,
    r: float | None = None,
    q: float | None = None,
    model: GexModel | None = None,
) -> VexProfile:
    """Compute net VEX, walls, and King for a chain cohort."""
    work = filter_chain_by_dte(chain, dte_max=dte_max)
    if work.empty:
        return VexProfile(
            net_vex=0.0,
            king_node=float("nan"),
            call_wall=float("nan"),
            put_wall=float("nan"),
            n_contracts=0,
            interpretation="undetermined",
        )

    sym = symbol or chain_symbol(chain)
    r_eff, q_eff, model_eff = resolve_gex_params(
        symbol=sym, asof=asof, r=r, q=q, model=model
    )

    with_vanna = add_bs_vanna_column(
        work, spot, symbol=sym, asof=asof, r=r_eff, q=q_eff, model=model_eff
    )
    per_strike = compute_dealer_vanna_exposure(with_vanna, spot)
    net = total_net_vex(per_strike)
    call_col = per_strike["call_vex"] if "call_vex" in per_strike.columns else pd.Series(dtype=float)
    put_col = per_strike["put_vex"] if "put_vex" in per_strike.columns else pd.Series(dtype=float)
    king = (
        float(per_strike["net_vex"].abs().idxmax())
        if not per_strike.empty
        else float("nan")
    )
    call_w = float(call_col.idxmax()) if not call_col.empty else float("nan")
    put_w = float(put_col.idxmin()) if not put_col.empty else float("nan")
    return VexProfile(
        net_vex=net,
        king_node=king,
        call_wall=call_w,
        put_wall=put_w,
        n_contracts=len(work),
        interpretation=vanna_interpretation(net),
    )


def _net_gex_at_spot(
    chain: pd.DataFrame,
    spot: float,
    *,
    r: float,
    q: float,
    model: GexModel,
    dealer_sign: Mapping[str, int],
    multiplier: int,
    sign_arr: np.ndarray,
) -> float:
    """Fast scalar net GEX without per-strike pivoting.

    Inner loop of `gamma_flip_level`: skips the pivot_table that
    `compute_dealer_gamma_exposure` does (~30x speedup at typical chain sizes
    and a 41-point grid, on the ~600k-row Philipp Dubach SPY corpus this is
    the difference between a 30-min build and a 3-min build).

    The caller is responsible for pre-computing `sign_arr` once (mapping each
    row's `right` → ±1) so we don't redo that hashing on every grid point.
    """
    if chain.empty:
        return 0.0
    t = effective_time_to_expiry_years(chain)
    gammas = contract_gamma_spot(
        spot=spot,
        strike=chain["strike"].to_numpy(dtype="float64"),
        time_to_expiry=t,
        volatility=chain["implied_volatility"].to_numpy(dtype="float64"),
        r=r,
        q=q,
        model=model,
    )
    oi = chain["open_interest"].to_numpy(dtype="float64")
    contract_gex = gammas * oi * multiplier * spot * spot
    return float(np.nansum(contract_gex * sign_arr))


@dataclass(frozen=True)
class GammaProfilePoint:
    """Total dealer net GEX at a hypothetical spot (SpotGamma profile view)."""

    spot: float
    net_gex: float
    net_gex_bn: float


def compute_gamma_profile_curve(
    chain: pd.DataFrame,
    spot: float,
    *,
    symbol: str | None = None,
    asof: date | None = None,
    r: float | None = None,
    q: float | None = None,
    model: GexModel | None = None,
    dealer_sign: Mapping[str, int] = DEFAULT_DEALER_SIGN,
    multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
    search_radius_pct: float = 0.10,
    n_search_points: int = 41,
) -> list[GammaProfilePoint]:
    """Net GEX vs hypothetical spot — SpotGamma \"gamma profile\" curve.

    Recomputes BS gamma at each grid spot (IV and OI fixed at snapshot).
    Values are in internal $/``$1`` move units; ``net_gex_bn`` applies the
    SpotGamma ×0.01 / 1e9 conversion (billions per 1% index move).
    """
    if chain.empty or not np.isfinite(spot) or spot <= 0:
        return []

    required = {"strike", "dte", "implied_volatility", "right", "open_interest"}
    missing = required - set(chain.columns)
    if missing:
        raise ValueError(f"chain is missing required columns: {sorted(missing)}")

    sym = symbol or chain_symbol(chain)
    r_eff, q_eff, model_eff = resolve_gex_params(
        symbol=sym, asof=asof, r=r, q=q, model=model
    )

    sign_arr = chain["right"].map(dict(dealer_sign)).to_numpy(dtype="float64")
    if np.isnan(sign_arr).any():
        bad = chain.loc[pd.isna(chain["right"].map(dict(dealer_sign))), "right"].unique().tolist()
        raise ValueError(f"unrecognized right values not in dealer_sign: {bad}")

    grid = np.linspace(
        spot * (1.0 - search_radius_pct),
        spot * (1.0 + search_radius_pct),
        n_search_points,
    )
    net_at_grid = np.fromiter(
        (
            _net_gex_at_spot(
                chain,
                float(s_grid),
                r=r_eff,
                q=q_eff,
                model=model_eff,
                dealer_sign=dealer_sign,
                multiplier=multiplier,
                sign_arr=sign_arr,
            )
            for s_grid in grid
        ),
        dtype="float64",
        count=len(grid),
    )
    return [
        GammaProfilePoint(
            spot=float(s),
            net_gex=float(g),
            net_gex_bn=net_gex_bn_per_1pct(float(g)),
        )
        for s, g in zip(grid, net_at_grid)
    ]


def gamma_flip_level(
    chain: pd.DataFrame,
    spot: float,
    *,
    symbol: str | None = None,
    asof: date | None = None,
    r: float | None = None,
    q: float | None = None,
    model: GexModel | None = None,
    gamma_col: str = "bs_gamma",
    dealer_sign: Mapping[str, int] = DEFAULT_DEALER_SIGN,
    multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
    search_radius_pct: float = 0.10,
    n_search_points: int = 41,
) -> float:
    """The spot price at which total dealer net GEX would cross zero.

    Recomputes BS gamma at a grid of hypothetical spot prices in
    `[spot · (1 - r), spot · (1 + r)]` (default ±10%) and linearly interpolates
    the zero crossing. The intuition: at the flip level, dealer hedging stops
    being a damper and becomes an amplifier — the most-watched single number in
    0DTE positioning commentary.

    If the net GEX is monotone (same sign at both ends of the search interval),
    no crossing exists in the searched range and we return NaN. The caller can
    widen `search_radius_pct` or interpret "no flip in ±10%" as "we are
    deep in a single regime today".

    The chain must have `strike`, `dte`, `implied_volatility`, `right`,
    `open_interest`. `gamma_col` is recomputed on the fly at each grid point;
    if you pass `gamma_col="gamma"` (the dataset's static value) the result
    will be biased because that gamma doesn't update with hypothetical spot.
    For correctness with non-BS gamma sources, use `bs_gamma` here.

    Args:
        chain: snapshot option chain.
        spot: current spot price (anchor for the search grid).
        r, q: BS inputs.
        gamma_col: column name to recompute. Must be 'bs_gamma' for now —
            other gamma columns are static and would give wrong flip levels.
        dealer_sign: per-right sign convention.
        multiplier: contract multiplier.
        search_radius_pct: fractional spot range to search on each side.
        n_search_points: grid resolution. 41 points across ±10% = 0.5%
            increments, plenty for piecewise-linear interpolation.

    Returns:
        Flip-level spot price (float), or NaN if no zero crossing in range.
    """
    if gamma_col != "bs_gamma":
        raise ValueError(
            "gamma_flip_level requires recomputing gamma at hypothetical spots; "
            "static gamma columns (e.g. dataset 'gamma') would give wrong answers. "
            "Use gamma_col='bs_gamma'."
        )

    required = {"strike", "dte", "implied_volatility", "right", "open_interest"}
    missing = required - set(chain.columns)
    if missing:
        raise ValueError(f"chain is missing required columns: {sorted(missing)}")

    curve = compute_gamma_profile_curve(
        chain,
        spot,
        symbol=symbol,
        asof=asof,
        r=r,
        q=q,
        model=model,
        dealer_sign=dealer_sign,
        multiplier=multiplier,
        search_radius_pct=search_radius_pct,
        n_search_points=n_search_points,
    )
    if len(curve) < 2:
        return float("nan")

    grid = np.array([p.spot for p in curve], dtype="float64")
    net_at_grid = np.array([p.net_gex for p in curve], dtype="float64")

    signs = np.sign(net_at_grid)
    crossings = np.where(np.diff(signs) != 0)[0]
    if len(crossings) == 0:
        return float("nan")

    i = int(crossings[0])
    s0, s1 = grid[i], grid[i + 1]
    g0, g1 = net_at_grid[i], net_at_grid[i + 1]
    if g1 == g0:
        return float(s0)
    return float(s0 - g0 * (s1 - s0) / (g1 - g0))
