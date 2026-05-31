"""Walk-forward grid search for IC sizing: pin weights and/or regime multipliers.

No ML — small grids + Pareto frontier (OOS Sharpe vs max DD).

Examples:

    python scripts/sweep_pin_weights.py --symbol SPY --mode pin
    python scripts/sweep_pin_weights.py --symbol SPY --mode regime
    python scripts/sweep_pin_weights.py --symbol SPY --mode both
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from quant_lab.config import settings
from quant_lab.strategies.zdte_ic_conditional import (
    DEFAULT_PIN_TIER_WEIGHTS,
    DEFAULT_REGIME_MULTIPLIERS,
    PinWeightConfig,
    PinWeightResult,
    SizingResult,
    add_terminal_context,
    pick_stable_pin_weights,
    pick_stable_sizing,
    sweep_pin_weights,
    sweep_regime_multipliers,
)


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("^", "").replace("/", "_")


def _parse_grid(s: str) -> tuple[float, ...]:
    return tuple(float(x.strip()) for x in s.split(",") if x.strip())


def _load_trades(symbol: str) -> pd.DataFrame:
    trades_path = settings.paths.processed / "zdte_ic_daily" / f"{_safe_symbol(symbol)}_trades.parquet"
    if not trades_path.exists():
        print(
            f"missing {trades_path}\n"
            f"run: python scripts/run_zdte_ic_daily_backtest.py --symbol {symbol}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    trades = pd.read_parquet(trades_path)
    if "pin_tier" not in trades.columns:
        terminal_path = settings.paths.processed / "terminal" / f"{_safe_symbol(symbol)}.parquet"
        trades = add_terminal_context(trades, pd.read_parquet(terminal_path))
    return trades


def _print_pin_row(rank: int, row: PinWeightResult) -> None:
    c = row.config
    tag = " *" if row.is_pareto else ""
    print(
        f"{rank:3d}{tag}  "
        f"high={c.w_high:.2f} mid={c.w_mid:.2f} low={c.w_low:.2f}  "
        f"OOS_sh={row.oos_sharpe:6.2f}  maxDD={row.max_drawdown:6.2%}  "
        f"folds+= {row.folds_positive}/{row.n_folds}  total=${row.total_pnl:,.0f}"
    )


def _print_sizing_row(rank: int, row: SizingResult) -> None:
    c = row.config
    tag = " *" if row.is_pareto else ""
    p = c.pin
    print(
        f"{rank:3d}{tag}  "
        f"pin {p.w_high:.1f}/{p.w_mid:.1f}/{p.w_low:.2f}  "
        f"reg L/S/U={c.long_gamma_mult:.2f}/{c.short_gamma_mult:.2f}/{c.undetermined_mult:.2f}  "
        f"OOS_sh={row.oos_sharpe:6.2f}  maxDD={row.max_drawdown:6.2%}  "
        f"folds+= {row.folds_positive}/{row.n_folds}  total=${row.total_pnl:,.0f}"
    )


def _run_pin_sweep(trades: pd.DataFrame, args: argparse.Namespace) -> list[PinWeightResult]:
    return sweep_pin_weights(
        trades,
        w_high_grid=_parse_grid(args.w_high),
        w_mid_grid=_parse_grid(args.w_mid),
        w_low_grid=_parse_grid(args.w_low),
        oos_fraction=args.oos_fraction,
    )


def _run_regime_sweep(trades: pd.DataFrame, pin: PinWeightConfig, args: argparse.Namespace) -> list[SizingResult]:
    return sweep_regime_multipliers(
        trades,
        pin,
        short_gamma_grid=_parse_grid(args.short_gamma),
        undetermined_grid=_parse_grid(args.undetermined),
        oos_fraction=args.oos_fraction,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--mode", choices=("pin", "regime", "both"), default="both")
    parser.add_argument("--w-high", default="1.5,2.0,2.5,3.0")
    parser.add_argument("--w-mid", default="0.5,0.75,1.0,1.25")
    parser.add_argument("--w-low", default="0.25,0.5,0.75")
    parser.add_argument("--short-gamma", default="0.25,0.35,0.5,0.65,0.75")
    parser.add_argument("--undetermined", default="0.5,0.75")
    parser.add_argument("--oos-fraction", type=float, default=0.20)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args(argv)

    trades = _load_trades(args.symbol)
    default_pin = PinWeightConfig(
        w_high=DEFAULT_PIN_TIER_WEIGHTS["pin_high"],
        w_mid=DEFAULT_PIN_TIER_WEIGHTS["pin_mid"],
        w_low=DEFAULT_PIN_TIER_WEIGHTS["pin_low"],
    )

    best_pin = default_pin
    if args.mode in ("pin", "both"):
        pin_results = _run_pin_sweep(trades, args)
        ranked = sorted(pin_results, key=lambda r: r.oos_sharpe, reverse=True)
        print(f"=== Pin sweep: {args.symbol} ({len(trades)} trades, {len(pin_results)} configs) ===")
        for i, row in enumerate(ranked[: args.top], start=1):
            _print_pin_row(i, row)
        stable_pin = pick_stable_pin_weights(pin_results, min_folds_positive=3)
        if ranked:
            best_pin = ranked[0].config
        if stable_pin is not None:
            best_pin = stable_pin.config
            print(f"\nStable pin pick: {best_pin.w_high}/{best_pin.w_mid}/{best_pin.w_low}")
        print()

    if args.mode in ("regime", "both"):
        regime_results = _run_regime_sweep(trades, best_pin, args)
        ranked_r = sorted(regime_results, key=lambda r: r.oos_sharpe, reverse=True)
        print(
            f"=== Regime sweep (fixed pin {best_pin.w_high}/{best_pin.w_mid}/{best_pin.w_low}): "
            f"{len(regime_results)} configs ==="
        )
        baseline = next(
            (
                r
                for r in regime_results
                if r.config.short_gamma_mult == DEFAULT_REGIME_MULTIPLIERS["short_gamma"]
                and r.config.undetermined_mult == DEFAULT_REGIME_MULTIPLIERS["undetermined"]
            ),
            None,
        )
        if baseline is not None:
            b = baseline
            print(
                f"current default regime L/S/U=1.0/{DEFAULT_REGIME_MULTIPLIERS['short_gamma']}/"
                f"{DEFAULT_REGIME_MULTIPLIERS['undetermined']}: "
                f"OOS_sh={b.oos_sharpe:.2f}  maxDD={b.max_drawdown:.2%}"
            )
        for i, row in enumerate(ranked_r[: args.top], start=1):
            _print_sizing_row(i, row)
        stable_r = pick_stable_sizing(regime_results, min_folds_positive=3)
        if stable_r is not None:
            c = stable_r.config
            print(
                f"\nRecommended stable sizing: "
                f"pin {c.pin.w_high}/{c.pin.w_mid}/{c.pin.w_low}  "
                f"reg L/S/U={c.long_gamma_mult}/{c.short_gamma_mult}/{c.undetermined_mult}  "
                f"OOS_sh={stable_r.oos_sharpe:.2f}"
            )
        elif ranked_r:
            c = ranked_r[0].config
            print(
                f"\nBest OOS (no 3/5 fold stability): "
                f"reg L/S/U={c.long_gamma_mult}/{c.short_gamma_mult}/{c.undetermined_mult}  "
                f"OOS_sh={ranked_r[0].oos_sharpe:.2f}"
            )

        out_path = settings.paths.processed / "zdte_ic_daily" / f"{_safe_symbol(args.symbol)}_sizing_sweep.parquet"
        rows = []
        for r in regime_results:
            rows.append(
                {
                    "w_high": r.config.pin.w_high,
                    "w_mid": r.config.pin.w_mid,
                    "w_low": r.config.pin.w_low,
                    "long_gamma_mult": r.config.long_gamma_mult,
                    "short_gamma_mult": r.config.short_gamma_mult,
                    "undetermined_mult": r.config.undetermined_mult,
                    "oos_sharpe": r.oos_sharpe,
                    "max_drawdown": r.max_drawdown,
                    "folds_positive": r.folds_positive,
                    "total_pnl": r.total_pnl,
                    "is_pareto": r.is_pareto,
                }
            )
        pd.DataFrame(rows).to_parquet(out_path, index=False)
        print(f"wrote → {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
