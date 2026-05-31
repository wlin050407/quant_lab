"""Quality-check unit tests. No network."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_lab.quality.checks import (
    check_option_chain,
    check_snapshot_continuity,
    check_underlying,
)


def _good_underlying() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=10, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": np.linspace(100, 110, 10),
            "high": np.linspace(101, 111, 10),
            "low": np.linspace(99, 109, 10),
            "close": np.linspace(100, 110, 10),
            "adj_close": np.linspace(100, 110, 10),
            "volume": [1_000_000] * 10,
        },
        index=idx,
    )


def test_check_underlying_clean_dataframe_has_no_issues() -> None:
    rep = check_underlying(_good_underlying(), symbol="TEST")
    assert not rep.has_errors
    assert rep.issues == []


def test_check_underlying_detects_high_below_low() -> None:
    df = _good_underlying()
    df.iloc[3, df.columns.get_loc("high")] = 1.0
    rep = check_underlying(df, symbol="TEST")
    assert rep.has_errors
    assert any(i.code == "UND_HL_INVERTED" for i in rep.issues)


def test_check_underlying_flags_large_jump_as_warn() -> None:
    df = _good_underlying()
    df.iloc[5, df.columns.get_loc("close")] = 300.0
    rep = check_underlying(df, symbol="TEST")
    assert any(i.code == "UND_LARGE_JUMP" and i.severity == "warn" for i in rep.issues)


def _good_chain() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["X"] * 4,
            "expiry": pd.to_datetime(["2099-01-15"] * 4).date,
            "strike": [90.0, 100.0, 110.0, 120.0],
            "right": ["C", "C", "P", "P"],
            "dte": [30, 30, 30, 30],
            "bid": [10.0, 5.0, 5.0, 10.0],
            "ask": [10.1, 5.1, 5.1, 10.1],
            "last_price": [10.05, 5.05, 5.05, 10.05],
            "implied_volatility": [0.2, 0.25, 0.25, 0.2],
            "volume": [100, 200, 200, 100],
            "open_interest": [1000, 2000, 2000, 1000],
            "in_the_money": [True, False, True, False],
        }
    )


def test_check_option_chain_clean_returns_no_errors() -> None:
    rep = check_option_chain(_good_chain(), symbol="X", spot=100.0)
    assert not rep.has_errors


def test_check_option_chain_detects_crossed_quote_as_warn() -> None:
    chain = _good_chain()
    chain.loc[0, "ask"] = 1.0
    rep = check_option_chain(chain, symbol="X", spot=100.0)
    assert any(i.code == "OPT_CROSSED_QUOTES" for i in rep.issues)


def test_check_option_chain_detects_bad_right_as_error() -> None:
    chain = _good_chain()
    chain.loc[0, "right"] = "X"
    rep = check_option_chain(chain, symbol="X", spot=100.0)
    assert rep.has_errors
    assert any(i.code == "OPT_BAD_RIGHT" for i in rep.issues)


def test_check_option_chain_flags_iv_unreliable_at_expiry_as_warn() -> None:
    chain = _good_chain()
    chain.loc[0, "dte"] = 0
    chain.loc[0, "implied_volatility"] = 0.001
    chain.loc[1, "dte"] = 1
    chain.loc[1, "implied_volatility"] = 8.0
    rep = check_option_chain(chain, symbol="X", spot=100.0)
    matches = [i for i in rep.issues if i.code == "OPT_IV_UNRELIABLE_AT_EXPIRY"]
    assert len(matches) == 1
    assert matches[0].severity == "warn"
    assert matches[0].rows == 2


def test_check_option_chain_no_iv_unreliable_when_dte_gt_1() -> None:
    chain = _good_chain()
    chain["dte"] = 30
    chain.loc[0, "implied_volatility"] = 0.001
    rep = check_option_chain(chain, symbol="X", spot=100.0)
    assert not any(i.code == "OPT_IV_UNRELIABLE_AT_EXPIRY" for i in rep.issues)


def test_check_option_chain_expired_uses_snapshot_dte_not_today() -> None:
    """OPT_EXPIRED must fire on dte<0 (relative to snapshot), not relative to
    the current wall clock — otherwise re-checking an old snapshot floods
    false positives. Regression for the 5/20 snapshot read on 5/24 case.
    """
    chain = _good_chain()
    # Snapshot has only future-DTE contracts at the time it was taken.
    chain["dte"] = [5, 10, 15, 20]
    chain["expiry"] = pd.to_datetime(["1990-01-01"] * 4).date
    rep = check_option_chain(chain, symbol="X", spot=100.0)
    assert not any(i.code == "OPT_EXPIRED" for i in rep.issues)


def test_check_option_chain_expired_fires_on_negative_dte() -> None:
    chain = _good_chain()
    chain.loc[0, "dte"] = -1
    chain.loc[1, "dte"] = -3
    rep = check_option_chain(chain, symbol="X", spot=100.0)
    matches = [i for i in rep.issues if i.code == "OPT_EXPIRED"]
    assert len(matches) == 1
    assert matches[0].rows == 2


def _make_snapshot(date_str: str, total_oi: int) -> tuple[str, pd.DataFrame, pd.DataFrame]:
    chain = _good_chain()
    chain["open_interest"] = total_oi // len(chain)
    meta = pd.DataFrame([{"asof_utc": pd.Timestamp(date_str), "spot": 100.0}])
    return date_str, chain, meta


def test_check_snapshot_continuity_clean_sequence() -> None:
    snaps = [_make_snapshot(d, 4000) for d in ("2026-05-18", "2026-05-19", "2026-05-20")]
    rep = check_snapshot_continuity("X", snaps)
    assert not rep.has_errors
    assert all(i.severity != "warn" for i in rep.issues)


def test_check_snapshot_continuity_detects_missing_day() -> None:
    snaps = [_make_snapshot(d, 4000) for d in ("2026-05-18", "2026-05-25")]
    rep = check_snapshot_continuity("X", snaps)
    assert any(i.code == "CONT_MISSING_DAY" and i.severity == "warn" for i in rep.issues)


def test_check_snapshot_continuity_detects_field_drift() -> None:
    snaps = [_make_snapshot(d, 4000) for d in ("2026-05-18", "2026-05-19")]
    bad_date, bad_chain, bad_meta = snaps[1]
    snaps[1] = (bad_date, bad_chain.drop(columns=["dte"]), bad_meta)
    rep = check_snapshot_continuity("X", snaps)
    assert rep.has_errors
    assert any(i.code == "CONT_FIELD_DRIFT" for i in rep.issues)


def test_check_snapshot_continuity_detects_oi_jump() -> None:
    snaps = [
        _make_snapshot("2026-05-18", 4000),
        _make_snapshot("2026-05-19", 80000),
    ]
    rep = check_snapshot_continuity("X", snaps)
    assert any(i.code == "CONT_OI_JUMP" and i.severity == "warn" for i in rep.issues)


def test_check_snapshot_continuity_rejects_unsorted_input() -> None:
    snaps = [_make_snapshot(d, 4000) for d in ("2026-05-20", "2026-05-18")]
    rep = check_snapshot_continuity("X", snaps)
    assert rep.has_errors
    assert any(i.code == "CONT_UNSORTED" for i in rep.issues)


def test_check_snapshot_continuity_handles_single_snapshot() -> None:
    snaps = [_make_snapshot("2026-05-19", 4000)]
    rep = check_snapshot_continuity("X", snaps)
    assert not rep.has_errors
    assert any(i.code == "CONT_SINGLE_SNAPSHOT" for i in rep.issues)
