"""Pin Play @ King — Terminal playbook (``docs/PIN_PLAY_SPEC.md`` §3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from typing import Any, Literal

import numpy as np

from quant_lab.data.macro_calendar import macro_playbook_gate
from quant_lab.data.intraday_time import SESSION_CLOSE, SESSION_OPEN, hours_to_close, parse_time_of_day
from quant_lab.strategies.zdte_ic_conditional import pin_tier
from quant_lab.strategies.zdte_pin_fly_eod import wing_width_from_expected_move

SessionPhase = Literal[
    "pre_open",
    "read_map",
    "pre_entry",
    "entry_window",
    "manage",
    "closed",
]


@dataclass(frozen=True)
class PlaybookCheck:
    id: str
    label: str
    passed: bool
    detail: str
    weight: float | None = None


@dataclass(frozen=True)
class PlaybookExitRule:
    id: str
    label: str
    detail: str
    active: bool


@dataclass(frozen=True)
class PlaybookStructure:
    center: float
    center_source: str
    wing_width: float
    long_call: float
    long_put: float
    summary: str


@dataclass(frozen=True)
class PinPlaybook:
    session_phase: SessionPhase
    phase_title: str
    phase_detail: str
    clock_et: str
    hours_to_close: float
    size_multiplier: float
    pin_multiplier: float
    regime_multiplier: float
    gate_multiplier: float
    macro_multiplier: float
    checks: tuple[PlaybookCheck, ...]
    structure: PlaybookStructure | None
    exits: tuple[PlaybookExitRule, ...]
    trinity_score: float | None
    trinity_direction: str | None
    actionable: bool
    summary: str


def _pin_multiplier(pin_score: float) -> float:
    """Pin Play §3.5 pin tier."""
    if not np.isfinite(pin_score):
        return 0.25
    if pin_score >= 70.0:
        return 1.0
    if pin_score >= 50.0:
        return 0.5
    return 0.25


def _regime_multiplier(regime: str) -> float:
    """Pin Play §3.5 regime tier (short gamma → no vol selling)."""
    if regime == "long_gamma":
        return 1.0
    if regime == "short_gamma":
        return 0.0
    return 0.75


def _spot_in_play_range(
    spot: float,
    *,
    put_wall: float | None,
    call_wall: float | None,
    king: float | None,
    expected_move: float | None,
) -> bool:
    if not np.isfinite(spot):
        return False
    if (
        put_wall is not None
        and call_wall is not None
        and np.isfinite(put_wall)
        and np.isfinite(call_wall)
        and put_wall < spot < call_wall
    ):
        return True
    if (
        king is not None
        and expected_move is not None
        and np.isfinite(king)
        and np.isfinite(expected_move)
        and expected_move > 0
    ):
        return abs(spot - king) <= 0.5 * expected_move
    return False


def session_phase(time_of_day: str) -> tuple[SessionPhase, str, str]:
    """Map ET clock to Pin Play session phase."""
    tod = parse_time_of_day(time_of_day)
    open_m = SESSION_OPEN.hour * 60 + SESSION_OPEN.minute
    close_m = SESSION_CLOSE.hour * 60 + SESSION_CLOSE.minute
    cur_m = tod.hour * 60 + tod.minute

    if cur_m < open_m:
        return "pre_open", "Pre-market", "Map only — no entries before 09:30 ET"
    if cur_m < 10 * 60:
        return "read_map", "Read map", "Regime · King · pin · EM · walls (09:30–10:00)"
    if cur_m < 13 * 60:
        return "pre_entry", "Watch", "Monitor levels · entry window opens 13:00 ET"
    if cur_m < 14 * 60:
        return "entry_window", "Entry window", "Iron fly @ King if sizing > 0 (13:00–14:00)"
    if cur_m < close_m:
        return "manage", "Manage / exit", "Thesis cut 14:00 · 50% profit · flat by 15:30"
    return "closed", "Session closed", "No new trades until next session"


def _build_structure(
    *,
    spot: float,
    king: float | None,
    magnet_strike: float | None,
    max_pain: float | None,
    expected_move: float | None,
    spx_notional: bool,
) -> PlaybookStructure | None:
    center: float | None = None
    source = "magnet"
    if magnet_strike is not None and np.isfinite(magnet_strike):
        center = float(magnet_strike)
        if king is not None and np.isfinite(king) and abs(center - king) <= 0.51:
            source = "king"
        elif max_pain is not None and np.isfinite(max_pain) and abs(center - max_pain) <= 0.51:
            source = "max_pain"
        else:
            source = "magnet"
    elif king is not None and np.isfinite(king):
        center = float(king)
        source = "king"
    elif max_pain is not None and np.isfinite(max_pain):
        center = float(max_pain)
        source = "max_pain"
    elif np.isfinite(spot):
        center = float(round(spot / 5.0) * 5.0) if spx_notional else float(spot)
        source = "spot"
    if center is None:
        return None

    wing = wing_width_from_expected_move(
        expected_move if expected_move is not None else float("nan"),
        spx_notional=spx_notional,
    )
    long_call = center + wing
    long_put = center - wing
    sym = "SPX" if spx_notional else "SPY"
    summary = (
        f"Short iron fly @ {center:.0f} · wings ±{wing:.0f}pt "
        f"({long_put:.0f}P / {center:.0f} body / {long_call:.0f}C)"
    )
    return PlaybookStructure(
        center=center,
        center_source=source,
        wing_width=wing,
        long_call=long_call,
        long_put=long_put,
        summary=summary,
    )


def _exit_rules(session_phase_id: SessionPhase) -> tuple[PlaybookExitRule, ...]:
    in_trade = session_phase_id in ("manage", "entry_window")
    thesis_active = session_phase_id == "manage"
    return (
        PlaybookExitRule(
            id="profit_50",
            label="50% max profit",
            detail="Take profit at half of entry credit",
            active=in_trade,
        ),
        PlaybookExitRule(
            id="stop_2x",
            label="2× credit stop",
            detail="Exit if loss reaches 2× entry credit",
            active=in_trade,
        ),
        PlaybookExitRule(
            id="stop_em_flip",
            label="EM / flip break",
            detail="Spot closes beyond expected move or gamma flip",
            active=in_trade,
        ),
        PlaybookExitRule(
            id="time_1400",
            label="14:00 thesis cut",
            detail="Close if pin thesis not working by 14:00 ET",
            active=thesis_active,
        ),
        PlaybookExitRule(
            id="time_1530",
            label="15:30 force flat",
            detail="Power hour gamma — no overnight 0DTE",
            active=thesis_active,
        ),
    )


def build_pin_playbook(
    *,
    symbol: str,
    session_date: date,
    time_of_day: str,
    regime: str,
    pin_score: float,
    pct_gex_dte1: float,
    spot: float,
    put_wall: float | None,
    call_wall: float | None,
    king: float | None,
    magnet_strike: float | None = None,
    max_pain: float | None,
    expected_move: float | None,
    gate_should_trade: bool,
    gate_reason: str,
    trinity_score: float | None = None,
    trinity_direction: str | None = None,
) -> PinPlaybook:
    """Assemble Pin Play playbook for Terminal right rail."""
    phase_id, phase_title, phase_detail = session_phase(time_of_day)
    hrs = hours_to_close(session_date, time_of_day)
    tod = parse_time_of_day(time_of_day)
    clock_et = tod.strftime("%H:%M")

    pin_mult = _pin_multiplier(pin_score)
    regime_mult = _regime_multiplier(regime)
    macro_mult, macro_detail = macro_playbook_gate(session_date)

    range_ok = _spot_in_play_range(
        spot,
        put_wall=put_wall,
        call_wall=call_wall,
        king=king,
        expected_move=expected_move,
    )
    pct_ok = np.isfinite(pct_gex_dte1) and pct_gex_dte1 >= 30.0
    regime_ok = regime == "long_gamma"
    pin_high = np.isfinite(pin_score) and pin_score >= 70.0

    gate_mult = 1.0
    if not regime_ok:
        gate_mult = 0.0
    elif macro_mult <= 0.0:
        gate_mult = 0.0
    else:
        if not pin_high:
            gate_mult = min(gate_mult, 0.25)
        if not pct_ok:
            gate_mult = min(gate_mult, 0.5)
        if not range_ok:
            gate_mult = min(gate_mult, 0.25)

    size_mult = float(pin_mult * regime_mult * gate_mult)

    checks = (
        PlaybookCheck(
            id="regime",
            label="Long gamma regime",
            passed=regime_ok,
            detail="Short gamma → 0× (no premium selling)" if not regime_ok else "+γ dealers dampen",
            weight=0.0 if not regime_ok else regime_mult,
        ),
        PlaybookCheck(
            id="pin",
            label=f"Pin score {pin_score:.0f}" if np.isfinite(pin_score) else "Pin score",
            passed=pin_high,
            detail=f"Tier {pin_tier(pin_score)} · mult {pin_mult:.2f}×",
            weight=pin_mult,
        ),
        PlaybookCheck(
            id="pct_gex",
            label="0DTE GEX share",
            passed=pct_ok,
            detail=(
                f"{pct_gex_dte1:.0f}% of chain"
                if np.isfinite(pct_gex_dte1)
                else "pct_gex_dte1 unavailable"
            ),
            weight=1.0 if pct_ok else 0.5,
        ),
        PlaybookCheck(
            id="range",
            label="Range / King proximity",
            passed=range_ok,
            detail="Inside walls or within 0.5× EM of King",
            weight=1.0 if range_ok else 0.25,
        ),
        PlaybookCheck(
            id="macro",
            label="Macro calendar",
            passed=macro_mult > 0.0,
            detail=macro_detail or "No FOMC / CPI on session",
            weight=macro_mult,
        ),
        PlaybookCheck(
            id="gate",
            label="FlashAlpha gate",
            passed=gate_should_trade,
            detail=gate_reason,
            weight=1.0 if gate_should_trade else 0.0,
        ),
    )

    spx = symbol.replace("^", "") in ("SPX", "SPXW")
    structure = _build_structure(
        spot=spot,
        king=king,
        magnet_strike=magnet_strike,
        max_pain=max_pain,
        expected_move=expected_move,
        spx_notional=spx,
    )

    entry_allowed = (
        phase_id == "entry_window"
        and size_mult > 0.0
        and gate_should_trade
        and regime_ok
    )
    if entry_allowed:
        summary = f"Entry OK · size {size_mult:.2f}× — {structure.summary if structure else 'structure n/a'}"
    elif phase_id == "entry_window" and size_mult <= 0:
        summary = "Entry window open but sizing is 0× — sit out or reduce"
    elif phase_id == "manage":
        summary = f"Manage open fly · target size reference {size_mult:.2f}× at entry"
    elif phase_id == "pre_entry":
        summary = f"Pre-entry · projected size {size_mult:.2f}× if gates hold at 13:00"
    else:
        summary = phase_detail

    return PinPlaybook(
        session_phase=phase_id,
        phase_title=phase_title,
        phase_detail=phase_detail,
        clock_et=clock_et,
        hours_to_close=float(hrs),
        size_multiplier=size_mult,
        pin_multiplier=pin_mult,
        regime_multiplier=regime_mult,
        gate_multiplier=gate_mult,
        macro_multiplier=macro_mult,
        checks=checks,
        structure=structure,
        exits=_exit_rules(phase_id),
        trinity_score=trinity_score,
        trinity_direction=trinity_direction,
        actionable=entry_allowed,
        summary=summary,
    )


def pin_playbook_to_dict(playbook: PinPlaybook) -> dict[str, Any]:
    """JSON-serializable playbook payload."""
    data = asdict(playbook)
    if playbook.structure is not None:
        data["structure"] = asdict(playbook.structure)
    data["checks"] = [asdict(c) for c in playbook.checks]
    data["exits"] = [asdict(e) for e in playbook.exits]
    return data
