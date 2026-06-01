"""Tests for GEX rate / model resolution."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quant_lab.factors.gex import black76_gamma, bs_gamma
from quant_lab.factors.rates import (
    is_index_underlying,
    normalize_underlying_symbol,
    resolve_gex_inputs,
)


def test_normalize_spx_aliases() -> None:
    assert normalize_underlying_symbol("^SPX") == "SPX"
    assert normalize_underlying_symbol("SPXW") == "SPX"


def test_index_uses_black76_model() -> None:
    inp = resolve_gex_inputs("^SPX")
    assert inp.model == "black76"
    assert is_index_underlying("SPX")


def test_spy_uses_bs_model() -> None:
    inp = resolve_gex_inputs("SPY")
    assert inp.model == "bs"


def test_black76_gamma_matches_bs_atm() -> None:
    s, k, t, vol, r, q = 5900.0, 5900.0, 3.0 / (365.0 * 6.5), 0.18, 0.05, 0.013
    b76 = black76_gamma(s, k, t, vol, r=r, q=q)
    bs = bs_gamma(s, k, t, vol, r=r, q=q)
    assert b76 == pytest.approx(bs, rel=5e-5)


def test_risk_free_rate_series_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quant_lab.config import settings

    series = tmp_path / "sofr.parquet"
    pd.DataFrame(
        {"date": ["2026-05-01", "2026-05-28"], "rate": [0.04, 0.045]}
    ).to_parquet(series, index=False)
    settings.positioning = type(settings.positioning)(
        risk_free_rate=0.05,
        risk_free_rate_series=series,
        dividend_yield=settings.positioning.dividend_yield,
    )
    inp = resolve_gex_inputs("SPY", asof=date(2026, 5, 29))
    assert inp.r == pytest.approx(0.045)
    assert inp.r_source == "series"
