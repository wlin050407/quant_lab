"""yfinance source unit tests — patches yfinance.Ticker, no network."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest


@pytest.fixture
def fake_history() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Adj Close": [100.5, 101.5, 102.5],
            "Volume": [1_000_000, 1_100_000, 1_200_000],
        },
        index=idx,
    )


@pytest.fixture
def fake_chain_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "contractSymbol": ["X240119C00100000", "X240119C00110000"],
            "strike": [100.0, 110.0],
            "lastPrice": [3.0, 0.5],
            "bid": [2.95, 0.45],
            "ask": [3.05, 0.55],
            "volume": [10, 5],
            "openInterest": [100, 50],
            "impliedVolatility": [0.22, 0.30],
            "inTheMoney": [True, False],
        }
    )


def test_get_underlying_normalizes_columns(monkeypatch, fake_history) -> None:
    from quant_lab.data import yfinance_source as yf_mod

    ticker = SimpleNamespace(
        history=lambda **kwargs: fake_history,
        options=("2024-01-19",),
        option_chain=lambda exp: SimpleNamespace(calls=pd.DataFrame(), puts=pd.DataFrame()),
    )
    monkeypatch.setattr(yf_mod.yf, "Ticker", lambda symbol: ticker)

    src = yf_mod.YFinanceSource(request_sleep_seconds=0.0)
    df = src.get_underlying("X")

    assert list(df.columns) == ["open", "high", "low", "close", "adj_close", "volume", "symbol"]
    assert str(df.index.tz) == "UTC"
    assert len(df) == 3


def test_get_option_chain_assembles_snapshot(
    monkeypatch, fake_history, fake_chain_df
) -> None:
    from quant_lab.data import yfinance_source as yf_mod

    opt_obj = SimpleNamespace(calls=fake_chain_df.copy(), puts=fake_chain_df.copy())
    ticker = SimpleNamespace(
        history=lambda **kwargs: fake_history,
        options=("2024-01-19",),
        option_chain=lambda exp: opt_obj,
    )
    monkeypatch.setattr(yf_mod.yf, "Ticker", lambda symbol: ticker)

    src = yf_mod.YFinanceSource(request_sleep_seconds=0.0)
    snap = src.get_option_chain("X", max_expiries=1)

    assert snap.symbol == "X"
    assert snap.spot == pytest.approx(102.5)
    assert len(snap.chain) == 4
    assert set(snap.chain["right"].unique()) == {"C", "P"}
    assert snap.chain["volume"].dtype.name == "int64"


def test_get_option_chain_computes_dte_column(
    monkeypatch, fake_history, fake_chain_df
) -> None:
    """dte = expiry - ET market session date (NOT UTC date)."""
    from datetime import datetime, timezone

    from quant_lab.data import yfinance_source as yf_mod

    opt_obj = SimpleNamespace(calls=fake_chain_df.copy(), puts=fake_chain_df.copy())
    ticker = SimpleNamespace(
        history=lambda **kwargs: fake_history,
        options=("2099-01-19",),
        option_chain=lambda exp: opt_obj,
    )
    monkeypatch.setattr(yf_mod.yf, "Ticker", lambda symbol: ticker)

    fixed_now = datetime(2099, 1, 14, 12, 0, tzinfo=timezone.utc)

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is not None else fixed_now.replace(tzinfo=None)

    monkeypatch.setattr(yf_mod, "datetime", _FakeDateTime)

    src = yf_mod.YFinanceSource(request_sleep_seconds=0.0)
    snap = src.get_option_chain("X", max_expiries=1)

    assert "dte" in snap.chain.columns
    assert snap.chain["dte"].dtype.name == "int64"
    assert (snap.chain["dte"] == 5).all()


def test_get_option_chain_dte_uses_et_not_utc_near_midnight(
    monkeypatch, fake_history, fake_chain_df
) -> None:
    """A 17:00 PT run (= 00:00 UTC next day) still belongs to today's ET session.

    Regression for the bug that caused 5/19 EoD snapshots to be filed as 5/20
    when run after 20:00 ET.
    """
    from datetime import datetime, timezone

    from quant_lab.data import yfinance_source as yf_mod

    opt_obj = SimpleNamespace(calls=fake_chain_df.copy(), puts=fake_chain_df.copy())
    ticker = SimpleNamespace(
        history=lambda **kwargs: fake_history,
        options=("2099-01-20",),
        option_chain=lambda exp: opt_obj,
    )
    monkeypatch.setattr(yf_mod.yf, "Ticker", lambda symbol: ticker)

    # 2099-01-20 00:30 UTC = 2099-01-19 19:30 ET — still Jan 19 in market terms.
    fixed_now = datetime(2099, 1, 20, 0, 30, tzinfo=timezone.utc)

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is not None else fixed_now.replace(tzinfo=None)

    monkeypatch.setattr(yf_mod, "datetime", _FakeDateTime)

    src = yf_mod.YFinanceSource(request_sleep_seconds=0.0)
    snap = src.get_option_chain("X", max_expiries=1)

    # Expiry 2099-01-20, ET session date 2099-01-19 → dte = 1, NOT 0 or -1.
    assert (snap.chain["dte"] == 1).all()


def test_get_option_expiries_raises_when_empty(monkeypatch) -> None:
    from quant_lab.data import yfinance_source as yf_mod

    ticker = SimpleNamespace(history=lambda **kwargs: pd.DataFrame(), options=())
    monkeypatch.setattr(yf_mod.yf, "Ticker", lambda symbol: ticker)

    src = yf_mod.YFinanceSource(request_sleep_seconds=0.0)
    with pytest.raises(RuntimeError):
        src.get_option_expiries("X")
