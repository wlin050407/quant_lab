"""Philipp Dubach source unit tests — uses tiny synthetic parquet files, no network."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from quant_lab.data.base import (
    REQUIRED_OPTION_COLUMNS,
    REQUIRED_UNDERLYING_COLUMNS,
    market_date,
)
from quant_lab.data.philippdubach_source import (
    MIN_ROWS_PER_SNAPSHOT,
    OPTIONS_COLUMNS,
    _normalize_chain_frame,
    _right_from_type,
    _snapshot_asof,
    iter_option_snapshots,
    list_available_snapshot_dates,
    load_underlying_dataframe,
)


def _make_options_row(
    *,
    snap: date,
    expiry: date,
    strike: float,
    type_: str,
    bid: float = 1.0,
    ask: float = 1.05,
    iv: float = 0.2,
    delta: float = 0.5,
    gamma: float = 0.01,
    oi: int = 100,
    vol: int = 10,
    in_the_money: bool = False,
) -> dict:
    return {
        "contract_id": f"SPY{snap:%y%m%d}{type_[0].upper()}{int(strike * 1000):08d}",
        "symbol": "SPY",
        "expiration": pd.Timestamp(expiry),
        "strike": strike,
        "type": type_,
        "last": (bid + ask) / 2,
        "mark": (bid + ask) / 2,
        "bid": bid,
        "bid_size": 0,
        "ask": ask,
        "ask_size": 0,
        "volume": vol,
        "open_interest": oi,
        "date": pd.Timestamp(snap),
        "implied_volatility": iv,
        "delta": delta,
        "gamma": gamma,
        "theta": -0.01,
        "vega": 0.05,
        "rho": 0.02,
        "in_the_money": in_the_money,
    }


def _write_options_parquet(rows: list[dict], path: Path) -> Path:
    df = pd.DataFrame(rows, columns=list(OPTIONS_COLUMNS))
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, path)
    return path


def test_right_from_type_maps_call_and_put() -> None:
    assert _right_from_type("call") == "C"
    assert _right_from_type("put") == "P"
    assert _right_from_type("CALL") == "C"
    assert _right_from_type("Put") == "P"


def test_right_from_type_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        _right_from_type("foo")


def test_snapshot_asof_anchors_at_16_et() -> None:
    asof = _snapshot_asof(date(2024, 6, 14))
    assert asof.tzinfo is not None
    assert market_date(asof) == date(2024, 6, 14)
    et = asof.astimezone(ZoneInfo("America/New_York"))
    assert et.time() == time(16, 0)


def test_snapshot_asof_winter_dst_boundary() -> None:
    """Sanity: a January date should produce a 21:00 UTC stamp (EST = UTC-5)."""
    asof = _snapshot_asof(date(2024, 1, 10))
    assert asof.hour == 21
    assert market_date(asof) == date(2024, 1, 10)


def test_normalize_chain_frame_maps_required_columns() -> None:
    rows = [
        _make_options_row(snap=date(2024, 1, 5), expiry=date(2024, 1, 19), strike=475.0, type_="call"),
        _make_options_row(snap=date(2024, 1, 5), expiry=date(2024, 1, 19), strike=475.0, type_="put"),
    ]
    raw = pd.DataFrame(rows, columns=list(OPTIONS_COLUMNS))
    out = _normalize_chain_frame(raw, symbol="SPY")

    for col in REQUIRED_OPTION_COLUMNS:
        assert col in out.columns, f"missing required col {col}"

    assert set(out["right"].unique()) == {"C", "P"}
    assert out["volume"].dtype.name == "int64"
    assert out["open_interest"].dtype.name == "int64"
    assert out["in_the_money"].dtype.name == "boolean"
    assert (out["dte"] == 14).all()
    assert "delta" in out.columns
    assert "gamma" in out.columns
    assert "mark" in out.columns


def test_normalize_chain_frame_empty_input_returns_required_columns() -> None:
    raw = pd.DataFrame(columns=list(OPTIONS_COLUMNS))
    out = _normalize_chain_frame(raw, symbol="SPY")
    assert list(out.columns) == list(REQUIRED_OPTION_COLUMNS)
    assert len(out) == 0


def test_iter_option_snapshots_yields_per_day(tmp_path: Path) -> None:
    rows: list[dict] = []
    for snap in (date(2024, 1, 5), date(2024, 1, 8), date(2024, 1, 9)):
        for k in (470.0, 475.0, 480.0):
            for t in ("call", "put"):
                rows.append(
                    _make_options_row(
                        snap=snap, expiry=date(2024, 1, 19), strike=k, type_=t
                    )
                )
    parquet = _write_options_parquet(rows, tmp_path / "spy.parquet")

    snaps = list(iter_option_snapshots(parquet, symbol="SPY", skip_min_rows=0))
    assert [market_date(s.asof) for s in snaps] == [
        date(2024, 1, 5),
        date(2024, 1, 8),
        date(2024, 1, 9),
    ]
    for s in snaps:
        assert s.symbol == "SPY"
        assert len(s.chain) == 6
        for col in REQUIRED_OPTION_COLUMNS:
            assert col in s.chain.columns


def test_iter_option_snapshots_respects_date_window(tmp_path: Path) -> None:
    rows: list[dict] = []
    for snap in (date(2024, 1, 5), date(2024, 1, 8), date(2024, 1, 9)):
        rows.append(
            _make_options_row(snap=snap, expiry=date(2024, 1, 19), strike=475.0, type_="call")
        )
    parquet = _write_options_parquet(rows, tmp_path / "spy.parquet")

    snaps = list(
        iter_option_snapshots(
            parquet,
            symbol="SPY",
            start_date=date(2024, 1, 8),
            end_date=date(2024, 1, 8),
            skip_min_rows=0,
        )
    )
    assert len(snaps) == 1
    assert market_date(snaps[0].asof) == date(2024, 1, 8)


def test_iter_option_snapshots_drops_sparse_day(tmp_path: Path) -> None:
    """Synthetic 2024-01-15 MLK placeholder (2 rows) must be filtered out."""
    rows = [
        _make_options_row(snap=date(2024, 1, 15), expiry=date(2024, 1, 19), strike=475.0, type_="call"),
        _make_options_row(snap=date(2024, 1, 15), expiry=date(2024, 1, 19), strike=475.0, type_="put"),
    ]
    for k in (470.0, 472.0, 475.0, 478.0, 480.0):
        for t in ("call", "put"):
            rows.append(
                _make_options_row(snap=date(2024, 1, 16), expiry=date(2024, 1, 19), strike=k, type_=t)
            )
    parquet = _write_options_parquet(rows, tmp_path / "spy.parquet")

    snaps = list(iter_option_snapshots(parquet, symbol="SPY", skip_min_rows=5))
    assert [market_date(s.asof) for s in snaps] == [date(2024, 1, 16)]


def test_iter_option_snapshots_keeps_sparse_day_when_threshold_zero(tmp_path: Path) -> None:
    rows = [
        _make_options_row(snap=date(2024, 1, 15), expiry=date(2024, 1, 19), strike=475.0, type_="call"),
        _make_options_row(snap=date(2024, 1, 15), expiry=date(2024, 1, 19), strike=475.0, type_="put"),
    ]
    parquet = _write_options_parquet(rows, tmp_path / "spy.parquet")
    snaps = list(iter_option_snapshots(parquet, symbol="SPY", skip_min_rows=0))
    assert len(snaps) == 1


def test_list_available_snapshot_dates(tmp_path: Path) -> None:
    rows: list[dict] = []
    for snap in (date(2024, 1, 5), date(2024, 1, 8), date(2024, 1, 9)):
        rows.append(
            _make_options_row(snap=snap, expiry=date(2024, 1, 19), strike=475.0, type_="call")
        )
    parquet = _write_options_parquet(rows, tmp_path / "spy.parquet")

    dates = list_available_snapshot_dates(parquet, symbol="SPY")
    assert dates == [date(2024, 1, 5), date(2024, 1, 8), date(2024, 1, 9)]


def test_load_underlying_dataframe_shape(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "symbol": ["SPY", "SPY", "SPY"],
            "date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "open": [470.0, 471.5, 469.0],
            "high": [472.0, 472.5, 470.5],
            "low": [469.0, 470.0, 467.5],
            "close": [471.0, 470.5, 468.0],
            "adjusted_close": [471.0, 470.5, 468.0],
            "volume": [50_000_000, 52_000_000, 51_000_000],
            "dividend_amount": [0.0, 0.0, 0.0],
            "split_coefficient": [1.0, 1.0, 1.0],
            "created_at": ["2025-01-01"] * 3,
        }
    )
    path = tmp_path / "underlying.parquet"
    df.to_parquet(path)

    out = load_underlying_dataframe(path, symbol="SPY")
    assert str(out.index.tz) == "UTC"
    assert out.index.is_monotonic_increasing
    for col in REQUIRED_UNDERLYING_COLUMNS:
        assert col in out.columns
    assert (out["symbol"] == "SPY").all()
    assert out["volume"].dtype.name == "int64"


def test_load_underlying_dataframe_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_underlying_dataframe(tmp_path / "missing.parquet")
