"""Storage round-trip tests. No network."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from quant_lab.data.base import OptionChainSnapshot
from quant_lab.data.storage import (
    list_option_snapshots,
    load_option_chain,
    load_underlying,
    save_option_chain,
    save_underlying,
)


@pytest.fixture(autouse=True)
def _isolate_data_root(tmp_path, monkeypatch):
    from quant_lab import config as cfg

    new_paths = cfg.Paths(
        project_root=tmp_path,
        data_root=tmp_path / "data",
        raw=tmp_path / "data" / "raw",
        processed=tmp_path / "data" / "processed",
    )
    new_paths.ensure()
    monkeypatch.setattr(cfg.settings, "paths", new_paths)
    yield


def test_underlying_save_and_load_round_trip() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="B", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1.0, 2, 3, 4, 5],
            "high": [1.1, 2.1, 3.1, 4.1, 5.1],
            "low": [0.9, 1.9, 2.9, 3.9, 4.9],
            "close": [1.05, 2.05, 3.05, 4.05, 5.05],
            "adj_close": [1.05, 2.05, 3.05, 4.05, 5.05],
            "volume": [10, 20, 30, 40, 50],
            "symbol": ["X"] * 5,
        },
        index=idx,
    )
    df.index.name = "datetime"

    save_underlying(df, symbol="X")
    out = load_underlying("X")
    assert len(out) == 5
    assert list(out.columns) == list(df.columns)


def test_underlying_save_dedupes_on_reappend() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="B", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1.0, 2, 3],
            "high": [1.1, 2.1, 3.1],
            "low": [0.9, 1.9, 2.9],
            "close": [1.0, 2.0, 3.0],
            "adj_close": [1.0, 2.0, 3.0],
            "volume": [10, 20, 30],
            "symbol": ["X"] * 3,
        },
        index=idx,
    )
    df.index.name = "datetime"

    save_underlying(df, symbol="X")
    save_underlying(df, symbol="X")
    out = load_underlying("X")
    assert len(out) == 3


def test_option_chain_save_and_load() -> None:
    chain = pd.DataFrame(
        {
            "symbol": ["X", "X"],
            "expiry": pd.to_datetime(["2099-01-15", "2099-01-15"]).date,
            "strike": [100.0, 110.0],
            "right": ["C", "P"],
            "dte": [365, 365],
            "bid": [1.0, 2.0],
            "ask": [1.1, 2.1],
            "last_price": [1.05, 2.05],
            "implied_volatility": [0.2, 0.25],
            "volume": [10, 20],
            "open_interest": [100, 200],
            "in_the_money": [False, True],
        }
    )
    snap = OptionChainSnapshot(
        symbol="X",
        # 17:00 UTC == 13:00 ET — unambiguously 5/19 in market terms.
        asof=datetime(2026, 5, 19, 17, 0, tzinfo=timezone.utc),
        spot=105.0,
        chain=chain,
    )
    save_option_chain(snap)

    snapshots = list_option_snapshots("X")
    assert snapshots == ["2026-05-19"]

    loaded_chain, loaded_meta = load_option_chain("X", "2026-05-19")
    assert len(loaded_chain) == 2
    assert float(loaded_meta["spot"].iloc[0]) == pytest.approx(105.0)


def test_option_chain_snapshot_rejects_missing_columns() -> None:
    bad = pd.DataFrame({"strike": [100.0]})
    with pytest.raises(ValueError):
        OptionChainSnapshot(
            symbol="X",
            asof=datetime.now(tz=timezone.utc),
            spot=float(np.nan),
            chain=bad,
        )
