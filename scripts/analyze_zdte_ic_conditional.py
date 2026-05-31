"""Robustness analysis for Phase 3c conditional IC (M3).

Yearly breakdown + walk-forward folds on saved trades parquet.

Examples:

    python scripts/analyze_zdte_ic_conditional.py --symbol SPY
    python scripts/run_zdte_ic_conditional_backtest.py --symbol SPY  # refresh trades first
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from quant_lab.config import settings
from quant_lab.strategies.zdte_ic_conditional import (
    robustness_summary,
    walk_forward_folds,
    yearly_breakdown,
)


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("^", "").replace("/", "_")


def _print_yearly(rows: list) -> None:
    print("--- By calendar year (uncond vs cond) ---")
    print(f"{'year':>6}  {'u_n':>5} {'u_sh':>6} {'u_hit':>6}  {'c_n':>5} {'c_sh':>6} {'c_hit':>6}  {'d_sh':>6}")
    for row in rows:
        u, c = row.uncond, row.cond
        print(
            f"{row.year:6d}  "
            f"{u.n_trades:5d} {u.sharpe:6.2f} {u.hit_rate:6.1%}  "
            f"{c.n_trades:5d} {c.sharpe:6.2f} {c.hit_rate:6.1%}  "
            f"{row.sharpe_delta:+6.2f}"
        )
    print()


def _print_folds(folds: list) -> None:
    print("--- Walk-forward OOS folds (chronological) ---")
    print(f"{'fold':>4}  {'start':>10} {'end':>10}  {'u_n':>5} {'u_sh':>6}  {'c_n':>5} {'c_sh':>6}  {'d_sh':>6}")
    for fold in folds:
        u, c = fold.uncond, fold.cond
        print(
            f"{fold.fold:4d}  "
            f"{fold.oos_start:>10} {fold.oos_end:>10}  "
            f"{u.n_trades:5d} {u.sharpe:6.2f}  "
            f"{c.n_trades:5d} {c.sharpe:6.2f}  "
            f"{fold.sharpe_delta:+6.2f}"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--n-folds", type=int, default=5)
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--contracts", type=int, default=1)
    args = parser.parse_args(argv)

    path = settings.paths.processed / "zdte_ic_conditional" / f"{_safe_symbol(args.symbol)}_trades.parquet"
    if not path.exists():
        print(f"missing {path} — run run_zdte_ic_conditional_backtest.py first", file=sys.stderr)
        return 1

    trades = pd.read_parquet(path)
    n_cond = int(trades["conditional_pass"].sum())

    print(f"=== M3 robustness: {args.symbol} ===")
    print(f"trades: {len(trades)}  conditional pass: {n_cond}")
    print()

    yearly = yearly_breakdown(
        trades,
        initial_cash=args.initial_cash,
        contracts=args.contracts,
    )
    folds = walk_forward_folds(
        trades,
        n_folds=args.n_folds,
        initial_cash=args.initial_cash,
        contracts=args.contracts,
    )
    summary = robustness_summary(
        trades,
        n_folds=args.n_folds,
        initial_cash=args.initial_cash,
        contracts=args.contracts,
    )

    _print_yearly(yearly)
    _print_folds(folds)

    print("--- Summary ---")
    print(
        f"  years conditional Sharpe > unconditional: "
        f"{summary.n_years_cond_wins}/{summary.n_years}  "
        f"(median delta {summary.median_yearly_sharpe_delta:+.2f})"
    )
    print(
        f"  folds conditional Sharpe > unconditional: "
        f"{summary.n_folds_cond_wins}/{summary.n_folds}  "
        f"(median delta {summary.median_fold_sharpe_delta:+.2f})"
    )

    robust = (
        summary.n_years_cond_wins >= max(1, summary.n_years // 2)
        and summary.n_folds_cond_wins >= max(1, summary.n_folds // 2)
        and summary.median_fold_sharpe_delta > 0
    )
    print(f"  robustness check (majority years+folds, median fold delta>0): {'PASS' if robust else 'INCONCLUSIVE'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
