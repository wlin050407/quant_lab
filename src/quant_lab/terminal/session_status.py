"""US session phase helpers for terminal hold states (pre-open, early chain)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_time import session_datetime
from quant_lab.terminal.deploy import is_trading_weekday
from quant_lab.terminal.live_chain import market_today

SessionHoldReason = Literal["pre_market", "awaiting_chain"]

_HOLD_MESSAGES: dict[SessionHoldReason, str] = {
    "pre_market": "Market not open yet — 0DTE chain and Pin unlock at 09:30 ET.",
    "awaiting_chain": "Session open — waiting for first 0DTE quotes from ThetaData.",
}


def session_hold_message(reason: SessionHoldReason) -> str:
    return _HOLD_MESSAGES[reason]


def session_hold_reason(session: date, *, time_of_day: str) -> SessionHoldReason | None:
    """Why today's session has no chain yet (None → treat as real missing data / 404)."""
    del time_of_day  # reserved for future pin-slot gating
    if not is_trading_weekday(session) or session != market_today():
        return None

    now = datetime.now(MARKET_TZ)
    open_dt = session_datetime(session, "09:30:00")
    close_dt = session_datetime(session, "16:00:00")
    if now < open_dt:
        return "pre_market"
    if now >= close_dt:
        return None
    if now < open_dt + timedelta(minutes=5):
        return "awaiting_chain"
    return None
