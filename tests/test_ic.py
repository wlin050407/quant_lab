"""Unit tests for factors/ic.py."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.factors.ic import align_gex_with_underlying, compute_ic_table, spearman_ic


def test_spearman_ic_perfect_monotone() -> None:
    x = pd.Series([1, 2, 3, 4, 5], dtype="float64")
    y = pd.Series([10, 20, 30, 40, 50], dtype="float64")
    ic, n = spearman_ic(x, y)
    assert ic == pytest.approx(1.0)
    assert n == 5


def test_spearman_ic_drops_nan_pairs() -> None:
    x = pd.Series([1, 2, float("nan"), 4])
    y = pd.Series([1, 2, 3, float("nan")])
    ic, n = spearman_ic(x, y)
    assert n == 2
    assert ic == pytest.approx(1.0)


def test_align_gex_with_underlying_forward_return() -> None:
    gex = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "spot": [470.0, 472.0, 471.0],
            "net_gex_bs": [1e11, -1e11, 2e11],
            "flip_level_bs": [468.0, 473.0, 470.0],
        }
    )
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]).tz_localize("UTC")
    underlying = pd.DataFrame(
        {"close": [470.0, 472.0, 471.0, 475.0]},
        index=idx,
    )
    merged = align_gex_with_underlying(gex, underlying)
    assert len(merged) == 3
    row0 = merged.loc[merged["date"] == pd.Timestamp("2024-01-02")].iloc[0]
    assert row0["fwd_return"] == pytest.approx((472.0 - 470.0) / 470.0)
    assert bool(row0["long_gamma"]) is True
    assert row0["net_gex_bn"] == pytest.approx(100.0)


def test_compute_ic_table_shape() -> None:
    df = pd.DataFrame(
        {
            "net_gex_bn": [1, 2, 3, 4, 5],
            "spot_vs_flip_pct": [-1, -0.5, 0, 0.5, 1],
            "fwd_return": [0.01, 0.02, -0.01, 0.0, 0.03],
            "fwd_abs_return": [0.01, 0.02, 0.01, 0.0, 0.03],
        }
    )
    table = compute_ic_table(
        df,
        signals=["net_gex_bn", "spot_vs_flip_pct"],
        targets=["fwd_return", "fwd_abs_return"],
    )
    assert len(table) == 4
    assert set(table.columns) == {"signal", "target", "ic", "n"}


def test_ic_by_year_groups() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-06-01", "2023-07-01", "2024-01-01", "2024-02-01"]),
            "net_gex_bn": [1, 2, 3, 4],
            "fwd_abs_return": [0.01, 0.02, 0.03, 0.04],
        }
    )
    from quant_lab.factors.ic import ic_by_year

    out = ic_by_year(df, "net_gex_bn", "fwd_abs_return")
    assert set(out["year"]) == {2023, 2024}
    assert len(out) == 2
