"""M3 conditional IC parameter sensitivity sweep.

Re-filters saved IC trades under a grid of pin / setup / pct_gex thresholds
without re-simulating chains.

Examples:

    python scripts/sweep_m3_ic_conditional.py --symbol SPY
    python scripts/sweep_m3_ic_conditional.py --symbol SPY --min-pin 60 70 80 --top 10
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from quant_lab.backtest.engine import summarize_returns
from quant_lab.config import settings
from quant_lab.strategies.zdte_ic_conditional import (
    M3Config,
    M3SensitivityResult,
    enrich_trades_with_terminal,
    sweep_m3_parameters,
)
from quant_lab.strategies.zdte_ic_eod import split_is_oos, trades_to_daily_returns


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("^", "").replace("/", "_")


def _format_config(config: M3Config) -> str:
    return (
        f"pin>={config.min_pin:.0f}  "
        f"{config.setup_mode:<13}  "
        f"pct_gex>={config.min_pct_gex_dte1:.0f}"
    )


def _print_results(
    results: list[M3SensitivityResult],
    *,
    baseline_oos_sharpe: float,
    top: int,
) -> None:
    ranked = sorted(
        results,
        key=lambda r: (r.oos_sharpe_delta, r.folds_wins, r.n_trades),
        reverse=True,
    )

    print(f"{'rank':>4}  {'n':>4} {'oos_sh':>7} {'d_oos':>7} {'hit':>6}  "
          f"{'yrs':>5} {'flds':>5} {'med_d':>6}  config")
    for i, row in enumerate(ranked[:top], start=1):
        print(
            f"{i:4d}  "
            f"{row.n_trades:4d} {row.oos_sharpe:7.2f} {row.oos_sharpe_delta:+7.2f} "
            f"{row.oos_hit:6.1%}  "
            f"{row.years_wins:2d}/{row.n_years:<2d} "
            f"{row.folds_wins:2d}/{row.n_folds:<2d} "
            f"{row.median_fold_delta:+6.2f}  "
            f"{_format_config(row.config)}"
        )

    print()
    print(f"baseline unconditional OOS Sharpe: {baseline_oos_sharpe:.2f}")
    if ranked:
        best = ranked[0]
        stable = [
            r
            for r in ranked
            if r.folds_wins >= max(1, r.n_folds // 2 + 1)
            and r.median_fold_delta > 0
            and r.n_trades >= 30
        ]
        print(f"best by OOS delta: {_format_config(best.config)}  "
              f"(delta {best.oos_sharpe_delta:+.2f}, n={best.n_trades})")
        if stable:
            s = stable[0]
            print(f"best stable (majority folds + med delta>0): {_format_config(s.config)}  "
                  f"(delta {s.oos_sharpe_delta:+.2f}, n={s.n_trades})")
        else:
            print("no config passes stability heuristic (majority folds + median fold delta>0)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--min-pin", type=float, nargs="+", default=[60, 65, 70, 75, 80])
    parser.add_argument(
        "--setup-mode",
        choices=("pin_or_walls", "pin_only", "walls_only"),
        nargs="+",
        default=["pin_or_walls", "pin_only", "walls_only"],
    )
    parser.add_argument("--min-pct-gex", type=float, nargs="+", default=[20, 30, 40])
    parser.add_argument("--oos-fraction", type=float, default=0.20)
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--contracts", type=int, default=1)
    args = parser.parse_args(argv)

    trades_path = settings.paths.processed / "zdte_ic_conditional" / f"{_safe_symbol(args.symbol)}_trades.parquet"
    terminal_path = settings.paths.processed / "terminal" / f"{_safe_symbol(args.symbol)}.parquet"
    if not trades_path.exists():
        print(f"missing {trades_path} — run run_zdte_ic_conditional_backtest.py first", file=sys.stderr)
        return 1
    if not terminal_path.exists():
        print(f"missing {terminal_path}", file=sys.stderr)
        return 1

    trades = pd.read_parquet(trades_path)
    terminal = pd.read_parquet(terminal_path)
    enriched = enrich_trades_with_terminal(trades, terminal)

    baseline_ret = trades_to_daily_returns(
        enriched,
        initial_cash=args.initial_cash,
        contracts=args.contracts,
    )
    _, baseline_oos = split_is_oos(baseline_ret, oos_fraction=args.oos_fraction)
    baseline_oos_sharpe = summarize_returns(baseline_oos, initial_cash=args.initial_cash).sharpe

    results = sweep_m3_parameters(
        enriched,
        min_pins=tuple(args.min_pin),
        setup_modes=tuple(args.setup_mode),
        min_pct_gex_values=tuple(args.min_pct_gex),
        oos_fraction=args.oos_fraction,
        initial_cash=args.initial_cash,
        contracts=args.contracts,
        min_trades=args.min_trades,
    )

    print(f"=== M3 sensitivity: {args.symbol} ===")
    print(f"grid: {len(args.min_pin)} pin × {len(args.setup_mode)} setup × "
          f"{len(args.min_pct_gex)} pct_gex = {len(results)} valid configs")
    print()

    _print_results(results, baseline_oos_sharpe=baseline_oos_sharpe, top=args.top)

    out_path = settings.paths.processed / "zdte_ic_conditional" / f"{_safe_symbol(args.symbol)}_sensitivity.parquet"
    if results:
        rows = []
        for r in results:
            rows.append(
                {
                    "min_pin": r.config.min_pin,
                    "setup_mode": r.config.setup_mode,
                    "min_pct_gex_dte1": r.config.min_pct_gex_dte1,
                    "n_trades": r.n_trades,
                    "all_sharpe": r.all_sharpe,
                    "oos_sharpe": r.oos_sharpe,
                    "oos_hit": r.oos_hit,
                    "oos_sharpe_delta": r.oos_sharpe_delta,
                    "years_wins": r.years_wins,
                    "n_years": r.n_years,
                    "folds_wins": r.folds_wins,
                    "n_folds": r.n_folds,
                    "median_fold_delta": r.median_fold_delta,
                }
            )
        pd.DataFrame(rows).to_parquet(out_path, index=False)
        print(f"wrote grid → {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
