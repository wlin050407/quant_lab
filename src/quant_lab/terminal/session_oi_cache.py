"""Per-session reference OI cache for vendor pin / effective-OI mode."""

from __future__ import annotations

from datetime import date

import pandas as pd

from quant_lab.data.intraday_time import session_datetime

# (terminal_symbol, session_iso) -> reference OI frame
_session_reference_oi: dict[tuple[str, str], pd.DataFrame] = {}


def clear_session_oi_cache() -> None:
    """Clear in-memory reference OI (tests)."""
    _session_reference_oi.clear()


def get_reference_oi(terminal_symbol: str, session_date: date) -> pd.DataFrame | None:
    key = (terminal_symbol, session_date.isoformat())
    ref = _session_reference_oi.get(key)
    if ref is None:
        return None
    return ref.copy()


def maybe_store_reference_oi(
    terminal_symbol: str,
    session_date: date,
    time_of_day: str,
    oi: pd.DataFrame,
) -> None:
    """Store first OI snapshot at-or-after 09:30 as session reference for ΔOI effective OI."""
    if oi.empty:
        return
    key = (terminal_symbol, session_date.isoformat())
    if key in _session_reference_oi:
        return
    open_dt = session_datetime(session_date, "09:30:00")
    clock = session_datetime(session_date, time_of_day)
    if clock < open_dt:
        return
    work = oi.copy()
    if "right" not in work.columns or "strike" not in work.columns:
        return
    _session_reference_oi[key] = work[["strike", "right", "open_interest"]].copy()
