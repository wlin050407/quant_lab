"""Offline replay for Pin Center Fusion V1/V2 gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.config import settings
from quant_lab.data.gexbot_history_cache import (
    load_or_fetch_hist_day,
    snapshot_at_time,
    snapshot_at_unix,
)
from quant_lab.terminal.mm_structure import build_structure_snapshot, round_strike
from quant_lab.terminal.pin_center import PhysicalSnapshot, fuse_pin_center

ENTRY_CLOCK = "13:00:00"
CLOSE_CLOCK = "15:30:00"
V2_HORIZON_SEC = 30 * 60
V2_HIT_TOL_PTS = 5.0


@dataclass(frozen=True)
class SessionReplayRow:
    session_date: str
    close_spot: float
    king_k: float
    primary_k: float | None
    fused_k: float
    king_err: float
    primary_err: float | None
    fused_err: float
    primary_hit_30m: bool | None


def _terminal_path(symbol: str) -> Path:
    safe = symbol.replace("^", "").replace("/", "_")
    return settings.paths.processed / "terminal" / f"{safe}.parquet"


def _optional_float(val: Any) -> float | None:
    try:
        out = float(val)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def classic_from_hist_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    """Build minimal classic payload from slim hist row."""
    spot = _optional_float(snap.get("spot"))
    zero_gamma = _optional_float(snap.get("zero_gamma"))
    major_pos = _optional_float(snap.get("major_pos_vol")) or zero_gamma
    major_neg = _optional_float(snap.get("major_neg_vol"))
    sum_gex = _optional_float(snap.get("sum_gex_vol"))
    if sum_gex is None:
        sum_gex = 1_000_000.0 if zero_gamma is not None and spot is not None and spot > zero_gamma else -500_000.0
    return {
        "spot": spot,
        "zero_gamma": zero_gamma,
        "major_pos_vol": major_pos,
        "major_neg_vol": major_neg,
        "sum_gex_vol": sum_gex,
    }


def physical_from_terminal_row(row: pd.Series, *, spot: float) -> PhysicalSnapshot | None:
    king = _optional_float(row.get("king_dte1"))
    if king is None:
        return None
    return PhysicalSnapshot(
        spot=spot,
        king_bs=king,
        flip_bs=_optional_float(row.get("flip_dte1")),
        call_wall_bs=_optional_float(row.get("call_wall_dte1")),
        put_wall_bs=_optional_float(row.get("put_wall_dte1")),
        max_pain=_optional_float(row.get("max_pain_dte1")),
        pin_score=_optional_float(row.get("pin_score")),
        regime_local=str(row.get("regime", "undetermined")),
        pct_gex_dte1=_optional_float(row.get("pct_gex_dte1")),
        expected_move_1sd=_optional_float(row.get("expected_move_1sd")),
        magnet_strike=_optional_float(row.get("magnet_dte1")) or king,
    )


def replay_session(
    *,
    terminal_symbol: str,
    session_date: date,
    terminal_row: pd.Series,
    hist: pd.DataFrame,
    entry_clock: str = ENTRY_CLOCK,
    close_clock: str = CLOSE_CLOCK,
    pin_min: float = 70.0,
) -> SessionReplayRow | None:
    """Replay one session: 13:00 information set → close pin error."""
    physical = physical_from_terminal_row(terminal_row, spot=float(terminal_row.get("spot", np.nan)))
    if physical is None or physical.pin_score is None:
        return None
    if str(terminal_row.get("regime", "")) != "long_gamma":
        return None
    if physical.pin_score < pin_min:
        return None

    try:
        entry_snap = snapshot_at_time(hist, session_date, entry_clock)
        close_snap = snapshot_at_time(hist, session_date, close_clock)
    except (FileNotFoundError, IndexError, KeyError):
        return None

    close_spot = _optional_float(close_snap.get("spot"))
    if close_spot is None:
        return None

    classic = classic_from_hist_snapshot(entry_snap)
    entry_spot = _optional_float(classic.get("spot"))
    if entry_spot is not None:
        physical = PhysicalSnapshot(
            spot=entry_spot,
            king_bs=physical.king_bs,
            flip_bs=physical.flip_bs,
            call_wall_bs=physical.call_wall_bs,
            put_wall_bs=physical.put_wall_bs,
            max_pain=physical.max_pain,
            pin_score=physical.pin_score,
            regime_local=physical.regime_local,
            pct_gex_dte1=physical.pct_gex_dte1,
            expected_move_1sd=physical.expected_move_1sd,
            magnet_strike=physical.magnet_strike,
        )

    structure = build_structure_snapshot(
        terminal_symbol=terminal_symbol,
        classic=classic,
        orderflow={"spot": entry_spot or close_spot},
        spot=entry_spot,
    )
    decision = fuse_pin_center(physical, structure, minutes_to_close=150.0)

    king_k = round_strike(float(physical.king_bs))
    fused_k = round_strike(float(decision.pin_center))
    primary_k = (
        round_strike(float(structure.primary_mm_target.level))
        if structure is not None and structure.primary_mm_target is not None
        else None
    )

    primary_hit: bool | None = None
    if primary_k is not None:
        entry_unix = int(entry_snap.get("timestamp", 0))
        if entry_unix > 0:
            try:
                future_snap = snapshot_at_unix(hist, entry_unix + V2_HORIZON_SEC)
                future_spot = _optional_float(future_snap.get("spot"))
                if future_spot is not None:
                    primary_hit = abs(future_spot - primary_k) <= V2_HIT_TOL_PTS
            except (FileNotFoundError, IndexError):
                primary_hit = None

    return SessionReplayRow(
        session_date=session_date.isoformat(),
        close_spot=close_spot,
        king_k=king_k,
        primary_k=primary_k,
        fused_k=fused_k,
        king_err=abs(close_spot - king_k),
        primary_err=abs(close_spot - primary_k) if primary_k is not None else None,
        fused_err=abs(close_spot - fused_k),
        primary_hit_30m=primary_hit,
    )


def run_v1_replay(
    terminal_symbol: str,
    *,
    pin_min: float = 70.0,
    client: Any | None = None,
    max_sessions: int = 400,
) -> dict[str, Any]:
    """V1 gate: median |close - K| for king / primary / fused on GEXBot hist sessions."""
    path = _terminal_path(terminal_symbol)
    if not path.exists():
        return {"status": "skipped", "reason": "terminal_parquet_missing", "path": str(path)}

    terminal_df = pd.read_parquet(path)
    if terminal_df.empty:
        return {"status": "skipped", "reason": "empty_terminal"}

    if "date" in terminal_df.columns:
        terminal_df["date"] = pd.to_datetime(terminal_df["date"]).dt.date
    else:
        return {"status": "skipped", "reason": "no_date_column"}

    rows: list[SessionReplayRow] = []
    skipped_no_hist = 0
    for session_date in sorted(terminal_df["date"].unique())[-max_sessions:]:
        day_rows = terminal_df[terminal_df["date"] == session_date]
        if day_rows.empty:
            continue
        term_row = day_rows.iloc[-1]
        pin = _optional_float(term_row.get("pin_score"))
        if pin is None or pin < pin_min:
            continue
        if str(term_row.get("regime", "")) != "long_gamma":
            continue

        try:
            if client is not None:
                hist = load_or_fetch_hist_day(client, terminal_symbol, session_date)
            else:
                from quant_lab.data.gexbot_client import GexbotConfigError, get_gexbot_client

                try:
                    hist = load_or_fetch_hist_day(get_gexbot_client(), terminal_symbol, session_date)
                except GexbotConfigError:
                    return {
                        "status": "skipped",
                        "reason": "gexbot_api_key_missing",
                    }
        except (FileNotFoundError, OSError, ValueError):
            skipped_no_hist += 1
            continue

        replay = replay_session(
            terminal_symbol=terminal_symbol,
            session_date=session_date,
            terminal_row=term_row,
            hist=hist,
            pin_min=pin_min,
        )
        if replay is not None:
            rows.append(replay)

    if not rows:
        return {
            "status": "skipped",
            "reason": "no_replay_rows",
            "skipped_no_hist": skipped_no_hist,
        }

    king_errs = [r.king_err for r in rows]
    fused_errs = [r.fused_err for r in rows]
    primary_errs = [r.primary_err for r in rows if r.primary_err is not None]
    hits = [r.primary_hit_30m for r in rows if r.primary_hit_30m is not None]

    med_king = float(np.median(king_errs))
    med_fused = float(np.median(fused_errs))
    med_primary = float(np.median(primary_errs)) if primary_errs else None
    v2_rate = float(np.mean(hits)) if hits else None

    baseline = med_king if med_primary is None else min(med_king, med_primary)
    v1_pass = len(rows) >= 200 and med_fused <= baseline

    return {
        "status": "ok",
        "symbol": terminal_symbol,
        "n_sessions": len(rows),
        "skipped_no_hist": skipped_no_hist,
        "median_abs_close_minus_king": med_king,
        "median_abs_close_minus_primary": med_primary,
        "median_abs_close_minus_fused": med_fused,
        "v1_pass": v1_pass,
        "v1_partial": len(rows) < 200,
        "v1_blocker": None if len(rows) >= 200 else f"n_sessions={len(rows)} < 200",
        "v1_gate": "fused_median <= min(king, primary) and n>=200",
        "v2_primary_hit_30m_rate": v2_rate,
        "v2_pass": v2_rate is not None and v2_rate >= 0.55,
        "v2_partial": len(rows) < 200,
    }
