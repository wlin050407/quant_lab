"""Evidence grades tied to data provenance and sample quality."""

from __future__ import annotations

from typing import Literal

from quant_lab.factors.equity.liquidity_thresholds import grade_l0

Grade = Literal["A", "B", "C"]


def grade_l1(*, earnings_window: bool, macro_count: int, vol_regime: str) -> Grade:
    if earnings_window and macro_count > 0:
        return "C"
    if earnings_window or vol_regime == "elevated":
        return "B"
    return "A"


def grade_l2(*, intraday_source: str, n_bars: int) -> Grade:
    if intraday_source != "thetadata":
        return "C"
    if n_bars < 12:
        return "C"
    return "B"


def grade_l3(*, n_bars: int) -> Grade:
    if n_bars < 8:
        return "C"
    return "B"


def grade_l5(*, n_daily: int) -> Grade:
    if n_daily >= 200:
        return "A"
    if n_daily >= 60:
        return "B"
    return "C"


def grade_l6(*, n_contracts: int) -> Grade:
    if n_contracts >= 40:
        return "B"
    if n_contracts >= 10:
        return "C"
    return "C"


def grade_mid(*, earnings_risk: bool, options_available: bool, n_daily: int) -> Grade:
    if earnings_risk:
        return "C"
    if not options_available or n_daily < 60:
        return "B"
    return "B"


def grade_long(*, n_daily: int, rs_long_finite: bool) -> Grade:
    if n_daily >= 200 and rs_long_finite:
        return "A"
    if n_daily >= 120:
        return "B"
    return "C"
