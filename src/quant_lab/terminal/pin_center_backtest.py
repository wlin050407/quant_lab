"""Pin center resolution for EoD / intraday backtests (no live GEXBot WS)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.terminal.mm_structure import build_structure_snapshot
from quant_lab.terminal.pin_center import PhysicalSnapshot, PinCenterDecision, fuse_pin_center
from quant_lab.terminal.pin_center_replay import classic_from_hist_snapshot


@dataclass(frozen=True)
class TerminalPinFields:
    spot: float
    king_dte1: float
    flip_dte1: float | None
    max_pain_dte1: float | None
    pin_score: float | None
    regime: str
    pct_gex_dte1: float | None
    expected_move_1sd: float | None
    call_wall_dte1: float | None = None
    put_wall_dte1: float | None = None
    magnet_dte1: float | None = None


def terminal_fields_from_mapping(row: dict[str, Any] | pd.Series, *, spot: float) -> TerminalPinFields:
    """Build ``TerminalPinFields`` from terminal parquet row or intraday context dict."""

    def _f(key: str) -> float | None:
        if key not in row:
            return None
        try:
            val = float(row[key])
        except (TypeError, ValueError):
            return None
        return val if np.isfinite(val) else None

    king = _f("king_dte1")
    if king is None:
        raise ValueError("king_dte1 required for pin center backtest")
    return TerminalPinFields(
        spot=spot,
        king_dte1=king,
        flip_dte1=_f("flip_dte1"),
        max_pain_dte1=_f("max_pain_dte1"),
        pin_score=_f("pin_score"),
        regime=str(row.get("regime", "undetermined")),
        pct_gex_dte1=_f("pct_gex_dte1"),
        expected_move_1sd=_f("expected_move_1sd"),
        call_wall_dte1=_f("call_wall_dte1"),
        put_wall_dte1=_f("put_wall_dte1"),
        magnet_dte1=_f("magnet_dte1"),
    )


def classic_proxy_from_terminal(fields: TerminalPinFields) -> dict[str, Any]:
    """Minimal GEXBot-classic-shaped payload from local terminal fields (EoD proxy)."""
    sum_gex = 1_000_000.0 if fields.regime == "long_gamma" else -750_000.0
    if fields.pct_gex_dte1 is not None and np.isfinite(fields.pct_gex_dte1):
        sum_gex *= max(fields.pct_gex_dte1, 10.0) / 40.0
    return {
        "spot": fields.spot,
        "zero_gamma": fields.flip_dte1,
        "major_pos_vol": fields.king_dte1,
        "major_neg_vol": fields.put_wall_dte1,
        "sum_gex_vol": sum_gex,
        "max_priors": [],
    }


def _physical_from_fields(fields: TerminalPinFields) -> PhysicalSnapshot:
    magnet = fields.magnet_dte1 if fields.magnet_dte1 is not None else fields.king_dte1
    return PhysicalSnapshot(
        spot=fields.spot,
        king_bs=fields.king_dte1,
        flip_bs=fields.flip_dte1,
        call_wall_bs=fields.call_wall_dte1,
        put_wall_bs=fields.put_wall_dte1,
        max_pain=fields.max_pain_dte1,
        pin_score=fields.pin_score,
        regime_local=fields.regime,
        pct_gex_dte1=fields.pct_gex_dte1,
        expected_move_1sd=fields.expected_move_1sd,
        magnet_strike=magnet,
    )


def resolve_pin_center_for_backtest(
    fields: TerminalPinFields,
    *,
    terminal_symbol: str = "^SPX",
    classic: dict[str, Any] | None = None,
    minutes_to_close: float = 150.0,
    skip_when_blocked: bool = True,
) -> PinCenterDecision | None:
    """Fuse physical + structure for backtest fly center (Pin Center Fusion F4)."""
    classic = classic or classic_proxy_from_terminal(fields)
    structure = build_structure_snapshot(
        terminal_symbol=terminal_symbol,
        classic=classic,
        orderflow={"spot": fields.spot},
        spot=fields.spot,
    )
    decision = fuse_pin_center(
        _physical_from_fields(fields),
        structure,
        minutes_to_close=minutes_to_close,
    )
    if not np.isfinite(decision.pin_center):
        return None
    if skip_when_blocked and decision.entry_blocked:
        return None
    return decision


def resolve_pin_center_with_hist(
    fields: TerminalPinFields,
    hist: pd.DataFrame,
    session_date: date,
    *,
    terminal_symbol: str = "^SPX",
    entry_clock: str = "13:00:00",
    skip_when_blocked: bool = True,
) -> PinCenterDecision | None:
    """Use GEXBot hist @ entry for richer structure when cache is available."""
    from quant_lab.data.gexbot_history_cache import snapshot_at_time

    try:
        entry_snap = snapshot_at_time(hist, session_date, entry_clock)
    except (FileNotFoundError, IndexError, KeyError):
        return resolve_pin_center_for_backtest(
            fields,
            terminal_symbol=terminal_symbol,
            skip_when_blocked=skip_when_blocked,
        )
    classic = classic_from_hist_snapshot(entry_snap)
    spot = fields.spot
    entry_spot = classic.get("spot")
    if entry_spot is not None and np.isfinite(float(entry_spot)):
        spot = float(entry_spot)
        fields = TerminalPinFields(
            spot=spot,
            king_dte1=fields.king_dte1,
            flip_dte1=fields.flip_dte1,
            max_pain_dte1=fields.max_pain_dte1,
            pin_score=fields.pin_score,
            regime=fields.regime,
            pct_gex_dte1=fields.pct_gex_dte1,
            expected_move_1sd=fields.expected_move_1sd,
            call_wall_dte1=fields.call_wall_dte1,
            put_wall_dte1=fields.put_wall_dte1,
            magnet_dte1=fields.magnet_dte1,
        )
    return resolve_pin_center_for_backtest(
        fields,
        terminal_symbol=terminal_symbol,
        classic=classic,
        skip_when_blocked=skip_when_blocked,
    )


def resolve_pin_center_from_intraday_ctx(
    ctx: dict[str, float | str],
    *,
    spot: float,
    session_date: date,
    entry_time: str,
    terminal_symbol: str = "^SPX",
) -> PinCenterDecision | None:
    """Intraday chain context → fused pin center @ entry."""
    fields = terminal_fields_from_mapping(ctx, spot=spot)
    from quant_lab.data.intraday_time import hours_to_close

    minutes = hours_to_close(session_date, entry_time) * 60.0
    return resolve_pin_center_for_backtest(
        fields,
        terminal_symbol=terminal_symbol,
        minutes_to_close=minutes,
        skip_when_blocked=True,
    )
