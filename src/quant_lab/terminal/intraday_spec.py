"""ThetaData intraday / live chain specs for Terminal symbols."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class IntradayChainSpec:
    terminal_symbol: str
    option_root: str
    underlying_kind: Literal["index", "stock"]
    underlying_symbol: str
    strike_range: int = 80


_INTRADAY_SPECS: dict[str, IntradayChainSpec] = {
    "^SPX": IntradayChainSpec("^SPX", "SPXW", "index", "SPX", 80),
    "SPX": IntradayChainSpec("^SPX", "SPXW", "index", "SPX", 80),
    "SPY": IntradayChainSpec("SPY", "SPY", "stock", "SPY", 60),
    "QQQ": IntradayChainSpec("QQQ", "QQQ", "stock", "QQQ", 60),
}

LIVE_INTRADAY_SYMBOLS = frozenset(_INTRADAY_SPECS.keys())


def resolve_intraday_spec(symbol: str) -> IntradayChainSpec | None:
    """Return live/intraday chain spec when ``symbol`` supports ThetaData 0DTE."""
    if symbol in _INTRADAY_SPECS:
        return _INTRADAY_SPECS[symbol]
    normalized = symbol.replace("^", "")
    if normalized == "SPX":
        return _INTRADAY_SPECS["^SPX"]
    return None


def supports_live_intraday(symbol: str) -> bool:
    return resolve_intraday_spec(symbol) is not None
