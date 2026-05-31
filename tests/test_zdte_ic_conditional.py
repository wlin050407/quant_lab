"""Phase 3c conditional IC filter and tail stats tests."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.strategies.zdte_ic_conditional import (
    max_loss_per_trade,
    passes_m3_conditional_filter,
    period_stats,
    pin_tier,
    pin_tier_contract_weights,
    robustness_summary,
    stratified_stats,
    sweep_m3_parameters,
    trade_tail_stats,
    walk_forward_folds,
    weighted_trades_to_daily_returns,
    yearly_breakdown,
    PinWeightConfig,
    PinWeightResult,
    SizingConfig,
    contract_weights_from_sizing,
    evaluate_pin_weights,
    mark_pareto_frontier,
    pick_stable_pin_weights,
    sweep_pin_weights,
)


def test_conditional_accepts_pin_play_long_gamma() -> None:
    ok, reason = passes_m3_conditional_filter(
        regime="long_gamma",
        pin_score=75.0,
        pct_gex_dte1=45.0,
        spot=100.0,
        put_wall=95.0,
        call_wall=105.0,
    )
    assert ok is True
    assert reason == "ok"


def test_conditional_accepts_between_walls() -> None:
    ok, reason = passes_m3_conditional_filter(
        regime="long_gamma",
        pin_score=40.0,
        pct_gex_dte1=50.0,
        spot=100.0,
        put_wall=98.0,
        call_wall=102.0,
        setup_mode="walls_only",
    )
    assert ok is True
    assert reason == "ok"


def test_conditional_pin_only_mode() -> None:
    ok, _ = passes_m3_conditional_filter(
        regime="long_gamma",
        pin_score=40.0,
        pct_gex_dte1=50.0,
        spot=100.0,
        put_wall=98.0,
        call_wall=102.0,
        setup_mode="pin_only",
    )
    assert ok is False
    ok2, _ = passes_m3_conditional_filter(
        regime="long_gamma",
        pin_score=75.0,
        pct_gex_dte1=50.0,
        spot=100.0,
        put_wall=98.0,
        call_wall=102.0,
        setup_mode="pin_only",
    )
    assert ok2 is True


def test_sweep_m3_parameters() -> None:
    trades = pd.DataFrame(
        {
            "signal_date": ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"],
            "trade_date": ["2020-01-03", "2020-01-06", "2020-01-07", "2020-01-08"],
            "pnl_per_contract": [50.0, -20.0, 30.0, 40.0],
            "terminal_regime": ["long_gamma"] * 4,
            "pin_score": [75.0, 50.0, 80.0, 72.0],
            "pct_gex_dte1": [45.0, 45.0, 50.0, 35.0],
            "spot": [100.0, 100.0, 100.0, 100.0],
            "put_wall_dte1": [98.0, 98.0, 98.0, 98.0],
            "call_wall_dte1": [102.0, 102.0, 102.0, 102.0],
            "trinity_score": [float("nan")] * 4,
            "trinity_direction": [None] * 4,
        }
    )
    results = sweep_m3_parameters(trades, min_pins=(70.0,), setup_modes=("pin_only",), min_pct_gex_values=(30.0,), min_trades=2)
    assert len(results) == 1
    assert results[0].n_trades >= 2


def test_conditional_rejects_short_gamma() -> None:
    ok, reason = passes_m3_conditional_filter(
        regime="short_gamma",
        pin_score=80.0,
        pct_gex_dte1=50.0,
        spot=100.0,
        put_wall=95.0,
        call_wall=105.0,
    )
    assert ok is False
    assert reason == "not_long_gamma"


def test_conditional_rejects_low_dte_gex_share() -> None:
    ok, reason = passes_m3_conditional_filter(
        regime="long_gamma",
        pin_score=80.0,
        pct_gex_dte1=10.0,
        spot=100.0,
        put_wall=95.0,
        call_wall=105.0,
        min_pct_gex_dte1=40.0,
    )
    assert ok is False
    assert reason == "gate_failed"


def test_conditional_rejects_no_setup() -> None:
    ok, reason = passes_m3_conditional_filter(
        regime="long_gamma",
        pin_score=50.0,
        pct_gex_dte1=50.0,
        spot=110.0,
        put_wall=98.0,
        call_wall=102.0,
    )
    assert ok is False
    assert reason == "no_setup"


def test_conditional_trinity_required() -> None:
    ok, reason = passes_m3_conditional_filter(
        regime="long_gamma",
        pin_score=75.0,
        pct_gex_dte1=50.0,
        spot=100.0,
        put_wall=95.0,
        call_wall=105.0,
        trinity_score=50.0,
        trinity_direction="support",
        require_trinity=True,
        min_trinity=60.0,
    )
    assert ok is False
    assert reason == "trinity_low"


def test_max_loss_per_trade() -> None:
    loss = max_loss_per_trade(entry_credit=1.0, wing_width=2.0, commission_per_contract=0.0)
    assert loss == pytest.approx(100.0)


def test_trade_tail_stats_cvar() -> None:
    trades = pd.DataFrame(
        {
            "pnl_per_contract": [100.0, 50.0, -200.0, -300.0, -400.0],
            "entry_credit": [1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    tail = trade_tail_stats(trades, wing_width=2.0, commission_per_contract=0.0)
    assert tail.n_trades == 5
    assert tail.worst_pnl == pytest.approx(-400.0)
    assert tail.cvar_5pct == pytest.approx(-400.0)


def _sample_trades() -> pd.DataFrame:
    rows = []
    for i in range(24):
        year = 2020 + (i // 8)
        month = 1 + (i % 8)
        rows.append(
            {
                "trade_date": f"{year}-{month:02d}-15",
                "pnl_per_contract": 50.0 if i % 2 == 0 else -30.0,
                "conditional_pass": i % 3 != 0,
                "terminal_regime": "long_gamma" if i % 2 == 0 else "short_gamma",
                "pin_tier": "pin_high" if i % 5 == 0 else "pin_mid",
            }
        )
    return pd.DataFrame(rows)


def test_yearly_breakdown_and_walk_forward() -> None:
    trades = _sample_trades()
    yearly = yearly_breakdown(trades, min_trades=2)
    assert len(yearly) >= 2
    folds = walk_forward_folds(trades, n_folds=2, min_oos_trades=4)
    assert len(folds) >= 1
    summary = robustness_summary(trades, n_folds=2)
    assert summary.n_folds >= 1


def test_pin_tier() -> None:
    assert pin_tier(75.0) == "pin_high"
    assert pin_tier(50.0) == "pin_mid"
    assert pin_tier(20.0) == "pin_low"


def test_stratified_stats() -> None:
    trades = pd.DataFrame(
        {
            "trade_date": ["2020-01-03", "2020-01-06", "2020-01-07", "2020-01-08"],
            "pnl_per_contract": [50.0, -20.0, 30.0, 40.0],
        }
    )
    labels = pd.Series(["pin_high", "pin_high", "pin_low", "pin_low"])
    rows = stratified_stats(trades, labels, min_trades=2)
    assert len(rows) == 2


def test_regime_sizing_weights() -> None:
    trades = pd.DataFrame(
        {
            "trade_date": ["2020-01-03", "2020-01-06"],
            "pnl_per_contract": [100.0, -50.0],
            "pin_tier": ["pin_high", "pin_mid"],
            "terminal_regime": ["long_gamma", "short_gamma"],
        }
    )
    cfg = SizingConfig(
        pin=PinWeightConfig(2.0, 1.0, 0.5),
        long_gamma_mult=1.0,
        short_gamma_mult=0.5,
        undetermined_mult=0.75,
    )
    w = contract_weights_from_sizing(trades, cfg, base_contracts=1.0)
    assert w.iloc[0] == pytest.approx(2.0)
    assert w.iloc[1] == pytest.approx(0.5)


def test_period_stats_empty() -> None:
    stats = period_stats(pd.DataFrame())
    assert stats.n_trades == 0
    assert stats.sharpe == 0.0


def test_weighted_trades_to_daily_returns() -> None:
    trades = pd.DataFrame(
        {
            "trade_date": ["2020-01-03", "2020-01-06"],
            "pnl_per_contract": [100.0, -50.0],
            "pin_tier": ["pin_high", "pin_mid"],
        }
    )
    weights = pin_tier_contract_weights(trades, weights={"pin_high": 2.0, "pin_mid": 1.0})
    ret = weighted_trades_to_daily_returns(trades, weights, initial_cash=100_000.0)
    assert len(ret) == 2
    assert ret.iloc[0] == pytest.approx(200.0 / 100_000.0)
    assert ret.iloc[1] == pytest.approx(-50.0 / 100_000.0)


def _weight_sweep_trades() -> pd.DataFrame:
    rows = []
    for i in range(30):
        tier = "pin_high" if i % 5 == 0 else ("pin_low" if i % 7 == 0 else "pin_mid")
        pnl = 40.0 if tier == "pin_high" else (-30.0 if tier == "pin_mid" else 10.0)
        rows.append(
            {
                "trade_date": f"2020-{1 + (i % 12):02d}-15",
                "pnl_per_contract": pnl,
                "pin_tier": tier,
                "terminal_regime": "long_gamma" if i % 2 == 0 else "short_gamma",
            }
        )
    return pd.DataFrame(rows)


def test_sweep_pin_weights_monotonic() -> None:
    trades = _weight_sweep_trades()
    results = sweep_pin_weights(
        trades,
        w_high_grid=(2.0,),
        w_mid_grid=(1.0,),
        w_low_grid=(0.5,),
        n_folds=3,
    )
    assert len(results) == 1
    assert results[0].config.w_low == 0.5


def test_pareto_marks_nondominated() -> None:
    a = PinWeightResult(
        config=PinWeightConfig(2.0, 1.0, 0.5),
        n_trades=10,
        all_sharpe=1.0,
        oos_sharpe=1.0,
        oos_hit=0.6,
        max_drawdown=-0.05,
        folds_positive=3,
        n_folds=5,
        median_fold_sharpe=0.5,
        total_pnl=100.0,
    )
    b = PinWeightResult(
        config=PinWeightConfig(3.0, 1.0, 0.5),
        n_trades=10,
        all_sharpe=0.5,
        oos_sharpe=1.5,
        oos_hit=0.6,
        max_drawdown=-0.08,
        folds_positive=2,
        n_folds=5,
        median_fold_sharpe=0.3,
        total_pnl=80.0,
    )
    marked = mark_pareto_frontier([a, b])
    assert marked[0].is_pareto is True
    assert marked[1].is_pareto is True
