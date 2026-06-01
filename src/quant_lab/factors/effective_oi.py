"""Flow-adjusted open interest for intraday pin / GEX (FlashAlpha-aligned).

FlashAlpha ``/v1/flow/pin-risk`` uses **effective OI** = settled OI plus an
intraday flow delta (their OI simulator confidence ≈ 0.43).

ThetaData **Value** tier has no ``option_history_trade``; we proxy flow with
**|ΔOI| since a reference snapshot| (typically 10:00 ET vs 13:00 / 15:30).
When trade volume is available (Standard tier), pass cumulative session volume
instead of ``flow_delta``.

This module is stateless: DataFrames in, enriched DataFrame out.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# FlashAlpha OI simulator confidence (https://flashalpha.com/articles/live-0dte-pin-risk-api-intraday-flow-adjusted-magnet)
DEFAULT_FLOW_OI_CONFIDENCE = 0.43

OI_REFERENCE_COL = "oi_reference"
FLOW_OI_DELTA_COL = "flow_oi_delta"
FLOW_SOURCE_COL = "flow_source"
EFFECTIVE_OI_COL = "effective_open_interest"


def effective_open_interest(
    settled_oi: float | np.ndarray,
    flow_delta: float | np.ndarray,
    *,
    confidence: float = DEFAULT_FLOW_OI_CONFIDENCE,
    signed: bool = False,
) -> np.ndarray:
    """Settled OI plus confidence-weighted flow increment (non-negative).

    When ``signed=True``, ``flow_delta`` is net buy-minus-sell volume (FlashAlpha
    OI simulator). Unsigned proxies still use ``|flow|``.
    """
    settled = np.asarray(settled_oi, dtype="float64")
    flow = np.asarray(flow_delta, dtype="float64")
    flow = np.nan_to_num(flow, nan=0.0)
    settled = np.nan_to_num(settled, nan=0.0)
    weighted = flow if signed else np.abs(flow)
    return np.maximum(0.0, settled + confidence * weighted)


def _oi_lookup(reference: pd.DataFrame) -> pd.DataFrame:
    req = {"strike", "right", "open_interest"}
    missing = req - set(reference.columns)
    if missing:
        raise ValueError(f"reference chain missing columns: {sorted(missing)}")
    ref = reference[["strike", "right", "open_interest"]].copy()
    ref["strike"] = ref["strike"].astype("float64")
    ref["right"] = ref["right"].astype(str).str.upper().str[0]
    ref = ref.rename(columns={"open_interest": OI_REFERENCE_COL})
    return ref


def quote_size_table(quotes: pd.DataFrame) -> pd.DataFrame:
    """NBBO bid+ask size aggregated by (strike, right)."""
    if quotes.empty:
        return pd.DataFrame(columns=["strike", "right", "quote_size"])
    work = quotes.copy()
    work["right"] = work["right"].astype(str).str.upper().str[0]
    work["strike"] = work["strike"].astype("float64")
    if "bid_size" in work.columns:
        bid = pd.to_numeric(work["bid_size"], errors="coerce").fillna(0.0)
    else:
        bid = pd.Series(0.0, index=work.index)
    if "ask_size" in work.columns:
        ask = pd.to_numeric(work["ask_size"], errors="coerce").fillna(0.0)
    else:
        ask = pd.Series(0.0, index=work.index)
    work["quote_size"] = bid + ask
    return (
        work.groupby(["strike", "right"], as_index=False)["quote_size"]
        .max()
        .astype({"quote_size": "float64"})
    )


def flow_delta_from_quote_sizes(
    chain: pd.DataFrame,
    quotes_now: pd.DataFrame,
    quotes_reference: pd.DataFrame | None,
) -> pd.Series:
    """|quote_size(now) - quote_size(ref)| per row; absolute size if no ref."""
    now = quote_size_table(quotes_now)
    work = chain[["strike", "right"]].copy()
    work["strike"] = work["strike"].astype("float64")
    work["right"] = work["right"].astype(str).str.upper().str[0]
    merged = work.merge(now, on=["strike", "right"], how="left")
    sz_now = pd.to_numeric(merged["quote_size"], errors="coerce").fillna(0.0)

    if quotes_reference is None or quotes_reference.empty:
        return sz_now

    ref = quote_size_table(quotes_reference)
    merged_ref = work.merge(ref, on=["strike", "right"], how="left", suffixes=("", "_ref"))
    sz_ref = pd.to_numeric(merged_ref["quote_size"], errors="coerce").fillna(0.0)
    return (sz_now - sz_ref).abs()


def flow_delta_from_reference(
    chain: pd.DataFrame,
    reference: pd.DataFrame | None,
) -> pd.Series:
    """Per-row |OI(now) - OI(reference)|; zero when reference missing."""
    oi_now = pd.to_numeric(chain["open_interest"], errors="coerce").fillna(0.0)
    if reference is None or reference.empty:
        return pd.Series(0.0, index=chain.index, dtype="float64")

    work = chain[["strike", "right"]].copy()
    work["strike"] = work["strike"].astype("float64")
    work["right"] = work["right"].astype(str).str.upper().str[0]
    merged = work.merge(_oi_lookup(reference), on=["strike", "right"], how="left")
    ref_oi = pd.to_numeric(merged[OI_REFERENCE_COL], errors="coerce").fillna(0.0)
    return (oi_now - ref_oi).abs()


def enrich_chain_effective_oi(
    chain: pd.DataFrame,
    reference: pd.DataFrame | None = None,
    *,
    confidence: float = DEFAULT_FLOW_OI_CONFIDENCE,
    session_volume: pd.Series | None = None,
    session_signed_flow: pd.Series | None = None,
    quote_flow: pd.Series | None = None,
) -> pd.DataFrame:
    """Add ``flow_oi_delta``, ``effective_open_interest``; update ``volume`` proxy.

    ``session_signed_flow`` (Standard tier, Lee-Ready classified) overrides other
    proxies. ``session_volume`` is legacy unsigned cumulative volume.
    ``quote_flow`` uses |Δ NBBO size| when settled OI is static intraday.
    """
    if chain.empty:
        out = chain.copy()
        out[FLOW_OI_DELTA_COL] = pd.Series(dtype="float64")
        out[EFFECTIVE_OI_COL] = pd.Series(dtype="float64")
        out[FLOW_SOURCE_COL] = pd.Series(dtype="object")
        return out

    out = chain.copy()
    flow_source = "none"
    flow_signed = False
    if session_signed_flow is not None:
        flow = pd.to_numeric(session_signed_flow, errors="coerce").fillna(0.0)
        flow_source = "trade_signed"
        flow_signed = True
    elif session_volume is not None:
        flow = pd.to_numeric(session_volume, errors="coerce").fillna(0.0)
        flow_source = "trade"
    elif quote_flow is not None:
        flow = pd.to_numeric(quote_flow, errors="coerce").fillna(0.0)
        flow_source = "quote_size"
    else:
        flow = flow_delta_from_reference(out, reference)
        flow_source = "oi_delta" if reference is not None and not reference.empty else "none"

    settled = pd.to_numeric(out["open_interest"], errors="coerce").fillna(0.0)
    eff = effective_open_interest(
        settled.to_numpy(),
        flow.to_numpy(),
        confidence=confidence,
        signed=flow_signed,
    )

    out[FLOW_OI_DELTA_COL] = flow.astype("float64")
    out[EFFECTIVE_OI_COL] = np.round(eff).astype("int64")
    out[FLOW_SOURCE_COL] = flow_source
    # ``volume`` column doubles as flow proxy for downstream QC until trade tape exists.
    if "volume" not in out.columns or (out["volume"] == 0).all():
        out["volume"] = np.round(flow).astype("int64")
    return out


def chain_for_positioning(
    chain: pd.DataFrame,
    *,
    oi_mode: str = "settled",
) -> pd.DataFrame:
    """Return chain copy with ``open_interest`` swapped for effective OI when requested."""
    if oi_mode not in ("settled", "effective"):
        raise ValueError(f"oi_mode must be 'settled' or 'effective', got {oi_mode!r}")
    out = chain.copy()
    if oi_mode == "effective":
        if EFFECTIVE_OI_COL not in out.columns:
            raise ValueError(
                f"oi_mode='effective' requires {EFFECTIVE_OI_COL!r}; "
                "run enrich_intraday_chains_flow.py first"
            )
        out["open_interest"] = out[EFFECTIVE_OI_COL]
    return out
