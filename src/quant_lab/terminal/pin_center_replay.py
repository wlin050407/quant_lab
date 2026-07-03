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
    load_cached_hist_day,
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

# V1 gates (see docs/terminal/PIN_CENTER_FUSION_SPEC.md §8)
V1_FULL_MIN_N = 200
V1_HIST_PILOT_MIN_N = 30
V1_HIST_PILOT_COVERAGE = 0.5  # min n = max(30, floor(coverage * hist×terminal overlap))
V1_FUSED_BEATS_KING_MIN = 0.95

V2_FULL_MIN_N = 200
V2_HIST_PILOT_MIN_N = 30
V2_HIT_RATE_MIN = 0.55


def evaluate_v1_gate(
    *,
    n_sessions: int,
    n_hist_terminal_overlap: int,
    median_fused: float,
    median_king: float,
    median_primary: float | None,
    fused_beats_king_rate: float | None,
) -> dict[str, Any]:
    """Tiered V1: full (n≥200) or hist pilot (dense hist×terminal overlap sample)."""
    baseline = median_king if median_primary is None else min(median_king, median_primary)
    strike_ok = median_fused <= baseline
    king_ok = (
        fused_beats_king_rate is None
        or fused_beats_king_rate >= V1_FUSED_BEATS_KING_MIN
    )
    min_pilot_n = max(
        V1_HIST_PILOT_MIN_N,
        int(V1_HIST_PILOT_COVERAGE * n_hist_terminal_overlap),
    )
    full_pass = n_sessions >= V1_FULL_MIN_N and strike_ok and king_ok
    pilot_pass = (
        n_sessions >= min_pilot_n
        and strike_ok
        and king_ok
        and n_hist_terminal_overlap > 0
    )
    if full_pass:
        tier = "full"
    elif pilot_pass:
        tier = "hist_pilot"
    else:
        tier = "fail"
    blockers: list[str] = []
    if not strike_ok:
        blockers.append(
            f"median_fused={median_fused:.2f} > baseline={baseline:.2f}"
        )
    if not king_ok and fused_beats_king_rate is not None:
        blockers.append(
            f"fused_beats_king={fused_beats_king_rate:.1%} < {V1_FUSED_BEATS_KING_MIN:.0%}"
        )
    if not full_pass and not pilot_pass:
        if n_sessions < V1_FULL_MIN_N:
            blockers.append(f"n={n_sessions} < full_min={V1_FULL_MIN_N}")
        if n_sessions < min_pilot_n:
            blockers.append(f"n={n_sessions} < hist_pilot_min={min_pilot_n}")
    return {
        "v1_pass": full_pass or pilot_pass,
        "v1_tier": tier,
        "v1_strike_pass": strike_ok,
        "v1_full_pass": full_pass,
        "v1_hist_pilot_pass": pilot_pass,
        "v1_hist_pilot_min_n": min_pilot_n,
        "v1_blocker": None if (full_pass or pilot_pass) else "; ".join(blockers),
        "v1_gate_full": (
            f"fused_median <= min(king, primary) and n>={V1_FULL_MIN_N} "
            f"and fused_beats_king>={V1_FUSED_BEATS_KING_MIN:.0%}"
        ),
        "v1_gate_hist_pilot": (
            f"fused_median <= min(king, primary) and n>=max({V1_HIST_PILOT_MIN_N}, "
            f"{V1_HIST_PILOT_COVERAGE:.0%}*hist_terminal_overlap) "
            f"and fused_beats_king>={V1_FUSED_BEATS_KING_MIN:.0%}"
        ),
    }


def evaluate_v2_gate(
    *,
    n_sessions: int,
    n_hist_terminal_overlap: int,
    primary_hit_30m_rate: float | None,
) -> dict[str, Any]:
    """Tiered V2: full (n≥200) or hist pilot."""
    if primary_hit_30m_rate is None:
        return {
            "v2_pass": False,
            "v2_tier": "fail",
            "v2_blocker": "no_primary_hit_samples",
        }
    rate_ok = primary_hit_30m_rate >= V2_HIT_RATE_MIN
    min_pilot_n = max(
        V2_HIST_PILOT_MIN_N,
        int(V1_HIST_PILOT_COVERAGE * n_hist_terminal_overlap),
    )
    full_pass = n_sessions >= V2_FULL_MIN_N and rate_ok
    pilot_pass = (
        n_sessions >= min_pilot_n
        and rate_ok
        and n_hist_terminal_overlap > 0
    )
    tier = "full" if full_pass else ("hist_pilot" if pilot_pass else "fail")
    blockers: list[str] = []
    if not rate_ok:
        blockers.append(
            f"hit_rate={primary_hit_30m_rate:.1%} < {V2_HIT_RATE_MIN:.0%}"
        )
    if not full_pass and not pilot_pass:
        if n_sessions < V2_FULL_MIN_N:
            blockers.append(f"n={n_sessions} < full_min={V2_FULL_MIN_N}")
        if n_sessions < min_pilot_n:
            blockers.append(f"n={n_sessions} < hist_pilot_min={min_pilot_n}")
    return {
        "v2_pass": full_pass or pilot_pass,
        "v2_tier": tier,
        "v2_full_pass": full_pass,
        "v2_hist_pilot_pass": pilot_pass,
        "v2_blocker": None if (full_pass or pilot_pass) else "; ".join(blockers),
    }


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
    require_long_gamma: bool = True,
) -> SessionReplayRow | None:
    """Replay one session: 13:00 information set → close pin error."""
    physical = physical_from_terminal_row(terminal_row, spot=float(terminal_row.get("spot", np.nan)))
    if physical is None or physical.pin_score is None:
        return None
    if require_long_gamma and str(terminal_row.get("regime", "")) != "long_gamma":
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


def _hist_available_dates(terminal_symbol: str) -> list[date]:
    """Cached or manifest-listed GEXBot hist session dates."""
    from quant_lab.data.gexbot_hist_probe import load_coverage_manifest
    from quant_lab.data.gexbot_history_cache import hist_cache_path

    manifest = load_coverage_manifest()
    sym_key = terminal_symbol.replace("^", "").upper()
    if manifest is not None:
        man_sym = str(manifest.get("terminal_symbol", "")).replace("^", "").upper()
        if man_sym == sym_key and manifest.get("available_dates"):
            return sorted(date.fromisoformat(d) for d in manifest["available_dates"])

    root = hist_cache_path(terminal_symbol, date.today()).parent
    if not root.is_dir():
        return []
    out: list[date] = []
    for path in root.glob("*.parquet"):
        try:
            out.append(date.fromisoformat(path.stem))
        except ValueError:
            continue
    return sorted(out)


def _load_hist_for_replay(
    terminal_symbol: str,
    session_date: date,
    client: Any | None,
) -> pd.DataFrame:
    cached = load_cached_hist_day(terminal_symbol, session_date)
    if cached is not None and not cached.empty:
        return cached
    if client is not None:
        return load_or_fetch_hist_day(client, terminal_symbol, session_date)
    from quant_lab.data.gexbot_client import get_gexbot_client

    return load_or_fetch_hist_day(get_gexbot_client(), terminal_symbol, session_date)


def run_v1_replay(
    terminal_symbol: str,
    *,
    pin_min: float = 70.0,
    client: Any | None = None,
    max_sessions: int = 400,
    include_sessions: bool = False,
    hist_only: bool = True,
    long_gamma_only: bool = True,
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

    terminal_by_date = {d: terminal_df[terminal_df["date"] == d].iloc[-1] for d in terminal_df["date"].unique()}

    if hist_only:
        hist_dates = _hist_available_dates(terminal_symbol)
        session_dates = [d for d in hist_dates if d in terminal_by_date][-max_sessions:]
    else:
        session_dates = sorted(terminal_df["date"].unique())[-max_sessions:]

    rows: list[SessionReplayRow] = []
    skipped_no_hist = 0
    skipped_no_terminal = 0
    skipped_pin = 0
    skipped_regime = 0
    for session_date in session_dates:
        if session_date not in terminal_by_date:
            skipped_no_terminal += 1
            continue
        term_row = terminal_by_date[session_date]
        pin = _optional_float(term_row.get("pin_score"))
        if pin is None or pin < pin_min:
            skipped_pin += 1
            continue
        if long_gamma_only and str(term_row.get("regime", "")) != "long_gamma":
            skipped_regime += 1
            continue

        try:
            hist = _load_hist_for_replay(terminal_symbol, session_date, client)
        except (FileNotFoundError, OSError, ValueError):
            from quant_lab.data.gexbot_client import GexbotConfigError, get_gexbot_client

            if client is None:
                try:
                    get_gexbot_client()
                except GexbotConfigError:
                    return {"status": "skipped", "reason": "gexbot_api_key_missing"}
            skipped_no_hist += 1
            continue

        replay = replay_session(
            terminal_symbol=terminal_symbol,
            session_date=session_date,
            terminal_row=term_row,
            hist=hist,
            pin_min=pin_min,
            require_long_gamma=long_gamma_only,
        )
        if replay is not None:
            rows.append(replay)

    if not rows:
        return {
            "status": "skipped",
            "reason": "no_replay_rows",
            "skipped_no_hist": skipped_no_hist,
            "skipped_pin": skipped_pin,
            "skipped_regime": skipped_regime,
            "n_hist_dates": len(session_dates),
        }

    king_errs = [r.king_err for r in rows]
    fused_errs = [r.fused_err for r in rows]
    primary_errs = [r.primary_err for r in rows if r.primary_err is not None]
    hits = [r.primary_hit_30m for r in rows if r.primary_hit_30m is not None]

    med_king = float(np.median(king_errs))
    med_fused = float(np.median(fused_errs))
    med_primary = float(np.median(primary_errs)) if primary_errs else None
    v2_rate = float(np.mean(hits)) if hits else None

    fused_wins = sum(1 for r in rows if r.fused_err <= r.king_err)
    primary_wins = sum(
        1 for r in rows if r.primary_err is not None and r.fused_err <= r.primary_err
    )
    n_primary = sum(1 for r in rows if r.primary_err is not None)
    fused_beats_king_rate = float(fused_wins / len(rows)) if rows else None

    v1_eval = evaluate_v1_gate(
        n_sessions=len(rows),
        n_hist_terminal_overlap=len(session_dates),
        median_fused=med_fused,
        median_king=med_king,
        median_primary=med_primary,
        fused_beats_king_rate=fused_beats_king_rate,
    )
    v2_eval = evaluate_v2_gate(
        n_sessions=len(rows),
        n_hist_terminal_overlap=len(session_dates),
        primary_hit_30m_rate=v2_rate,
    )

    out: dict[str, Any] = {
        "status": "ok",
        "symbol": terminal_symbol,
        "pin_min": pin_min,
        "hist_only": hist_only,
        "long_gamma_only": long_gamma_only,
        "n_hist_dates_scanned": len(session_dates),
        "n_sessions": len(rows),
        "skipped_no_hist": skipped_no_hist,
        "skipped_pin": skipped_pin,
        "skipped_regime": skipped_regime,
        "median_abs_close_minus_king": med_king,
        "median_abs_close_minus_primary": med_primary,
        "median_abs_close_minus_fused": med_fused,
        "mean_abs_close_minus_king": float(np.mean(king_errs)) if king_errs else None,
        "mean_abs_close_minus_fused": float(np.mean(fused_errs)) if fused_errs else None,
        "fused_beats_king_rate": fused_beats_king_rate,
        "fused_beats_primary_rate": float(primary_wins / n_primary) if n_primary else None,
        "v2_primary_hit_30m_rate": v2_rate,
        **v1_eval,
        **v2_eval,
    }
    if include_sessions:
        out["sessions"] = [
            {
                "session_date": r.session_date,
                "close_spot": r.close_spot,
                "king_k": r.king_k,
                "primary_k": r.primary_k,
                "fused_k": r.fused_k,
                "king_err": r.king_err,
                "primary_err": r.primary_err,
                "fused_err": r.fused_err,
                "fused_beats_king": r.fused_err <= r.king_err,
                "primary_hit_30m": r.primary_hit_30m,
            }
            for r in rows
        ]
    return out
