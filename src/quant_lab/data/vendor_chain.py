"""Build ``OptionChainSnapshot`` from GEXBot + Unusual Whales."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import pandas as pd

from quant_lab.data.base import OptionChainSnapshot
from quant_lab.data.gexbot_client import GexbotClient, gexbot_ticker
from quant_lab.data.gexbot_history_cache import load_or_fetch_hist_day, snapshot_at_time
from quant_lab.data.intraday_time import session_datetime
from quant_lab.data.thetadata_chain import ChainMode, assemble_chain_from_quotes_oi
from quant_lab.data.unusualwhales_client import (
    UnusualWhalesClient,
    parse_flow_timestamp,
    parse_occ_option_symbol,
    uw_ticker,
)
from quant_lab.terminal.session_oi_cache import (
    get_reference_oi,
    maybe_store_reference_oi,
)

log = logging.getLogger(__name__)


def _contracts_to_quotes_oi(
    contracts: list[dict],
    *,
    terminal_symbol: str,
    session_date: date,
    spot: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Map UW option-contracts rows to quotes + OI frames for ``assemble_chain_from_quotes_oi``."""
    quote_rows: list[dict[str, float | str]] = []
    oi_rows: list[dict[str, float | str | int]] = []
    for row in contracts:
        sym = str(row.get("option_symbol", ""))
        try:
            _root, expiry, right, strike = parse_occ_option_symbol(sym)
        except ValueError:
            continue
        if expiry != session_date:
            continue
        bid = float(row.get("nbbo_bid") or 0.0)
        ask = float(row.get("nbbo_ask") or 0.0)
        if bid <= 0 and ask <= 0:
            last = float(row.get("last_price") or 0.0)
            if last > 0:
                bid = ask = last
        oi = int(float(row.get("open_interest") or 0))
        quote_rows.append(
            {
                "strike": strike,
                "right": right,
                "bid": bid,
                "ask": ask,
            }
        )
        oi_rows.append(
            {
                "strike": strike,
                "right": right,
                "open_interest": oi,
            }
        )
    quotes = pd.DataFrame(quote_rows)
    oi = pd.DataFrame(oi_rows)
    if quotes.empty:
        raise FileNotFoundError(
            f"no 0DTE UW contracts for {terminal_symbol} on {session_date}"
        )
    return quotes, oi


def _flow_to_session_frames(
    flow_rows: list[dict],
    *,
    session_date: date,
    time_of_day: str,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Cumulative per (strike, right) flow from UW intraday snapshots <= clock."""
    if not flow_rows:
        return None, None
    cutoff = session_datetime(session_date, time_of_day)
    vol_acc: dict[tuple[float, str], float] = {}
    signed_acc: dict[tuple[float, str], float] = {}
    for row in flow_rows:
        raw_ts = row.get("timestamp")
        if not raw_ts:
            continue
        ts = parse_flow_timestamp(str(raw_ts))
        if ts > cutoff:
            continue
        strike = float(row.get("strike", np.nan))
        if not np.isfinite(strike):
            continue
        call_vol = float(row.get("call_volume") or 0.0)
        put_vol = float(row.get("put_volume") or 0.0)
        call_ask = float(row.get("call_volume_ask_side") or 0.0)
        call_bid = float(row.get("call_volume_bid_side") or 0.0)
        put_ask = float(row.get("put_volume_ask_side") or 0.0)
        put_bid = float(row.get("put_volume_bid_side") or 0.0)
        vol_acc[(strike, "C")] = vol_acc.get((strike, "C"), 0.0) + call_vol
        vol_acc[(strike, "P")] = vol_acc.get((strike, "P"), 0.0) + put_vol
        signed_acc[(strike, "C")] = signed_acc.get((strike, "C"), 0.0) + (call_ask - call_bid)
        signed_acc[(strike, "P")] = signed_acc.get((strike, "P"), 0.0) + (put_ask - put_bid)

    if not vol_acc:
        return None, None
    vol_rows = [
        {"strike": k[0], "right": k[1], "volume": v} for k, v in vol_acc.items()
    ]
    signed_rows = [
        {"strike": k[0], "right": k[1], "signed_flow": v, "volume": vol_acc.get(k, 0.0)}
        for k, v in signed_acc.items()
    ]
    return pd.DataFrame(vol_rows), pd.DataFrame(signed_rows)


def _reference_oi_from_hist(
    gexbot: GexbotClient,
    terminal_symbol: str,
    session_date: date,
) -> pd.DataFrame | None:
    """Best-effort 09:30 OI reference via cached GEXBot hist (UW chain still supplies levels)."""
    try:
        hist = load_or_fetch_hist_day(gexbot, terminal_symbol, session_date)
        snap = snapshot_at_time(hist, session_date, "09:30:00")
        # GEXBot hist does not expose per-contract OI; reference comes from session cache instead.
        _ = snap
    except (FileNotFoundError, OSError, ValueError):
        return None
    return None


def build_0dte_chain_from_vendors(
    gexbot: GexbotClient,
    uw: UnusualWhalesClient | None,
    *,
    session_date: date,
    time_of_day: str,
    terminal_symbol: str,
    option_root: str,
    chain_mode: ChainMode = "pin",
    reference_oi: pd.DataFrame | None = None,
    use_hist_spot: bool = False,
) -> OptionChainSnapshot:
    """Merge GEXBot spot + UW contracts (+ optional flow) into standard chain snapshot."""
    ticker = gexbot_ticker(terminal_symbol)
    uw_sym = uw_ticker(terminal_symbol)

    def _gexbot_live() -> dict:
        return gexbot.classic(ticker, "gex_zero")

    def _uw_contracts() -> list[dict]:
        if uw is None:
            return []
        return uw.fetch_all_option_contracts(uw_sym, market_date=session_date)

    def _uw_flow() -> list[dict]:
        if uw is None or chain_mode != "full":
            return []
        return uw.flow_per_strike_intraday(uw_sym, market_date=session_date, limit=500)

    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_gex = pool.submit(_gexbot_live)
        fut_contracts = pool.submit(_uw_contracts)
        fut_flow = pool.submit(_uw_flow)
        classic = fut_gex.result()
        contracts = fut_contracts.result()
        flow_rows = fut_flow.result()

    if use_hist_spot:
        spot = float(
            snapshot_at_time(
                load_or_fetch_hist_day(gexbot, terminal_symbol, session_date),
                session_date,
                time_of_day,
            ).get("spot", np.nan)
        )
    else:
        spot = float(classic.get("spot", np.nan))

    if not np.isfinite(spot):
        raise ValueError(f"no spot from GEXBot for {terminal_symbol} @ {time_of_day}")

    if not contracts:
        raise FileNotFoundError(
            f"no UW option contracts for {uw_sym} on {session_date} — set UNUSUAL_WHALES_API_KEY"
        )

    quotes, oi = _contracts_to_quotes_oi(
        contracts,
        terminal_symbol=terminal_symbol,
        session_date=session_date,
        spot=spot,
    )

    ref_oi = reference_oi
    if chain_mode in ("pin", "full") and ref_oi is None:
        ref_oi = get_reference_oi(terminal_symbol, session_date)
    if chain_mode in ("pin", "full") and ref_oi is None:
        ref_oi = _reference_oi_from_hist(gexbot, terminal_symbol, session_date)

    session_vol: pd.DataFrame | None = None
    session_signed: pd.DataFrame | None = None
    if chain_mode == "full":
        session_vol, session_signed = _flow_to_session_frames(
            flow_rows,
            session_date=session_date,
            time_of_day=time_of_day,
        )

    snapshot = assemble_chain_from_quotes_oi(
        quotes,
        oi,
        spot=spot,
        session_date=session_date,
        time_of_day=time_of_day,
        terminal_symbol=terminal_symbol,
        option_root=option_root,
        reference_oi=ref_oi,
        session_volume=session_vol,
        session_signed_flow=session_signed,
    )
    maybe_store_reference_oi(terminal_symbol, session_date, time_of_day, oi)
    return snapshot


def vendor_levels_from_classic(classic: dict) -> dict[str, float | None]:
    """Extract vendor flip/walls for API meta overlay."""
    def _f(key: str) -> float | None:
        val = classic.get(key)
        try:
            out = float(val)
        except (TypeError, ValueError):
            return None
        return out if np.isfinite(out) else None

    return {
        "zero_gamma": _f("zero_gamma"),
        "major_pos_oi": _f("major_pos_oi"),
        "major_neg_oi": _f("major_neg_oi"),
        "major_pos_vol": _f("major_pos_vol"),
        "major_neg_vol": _f("major_neg_vol"),
        "sum_gex_oi": _f("sum_gex_oi"),
        "sum_gex_vol": _f("sum_gex_vol"),
    }
