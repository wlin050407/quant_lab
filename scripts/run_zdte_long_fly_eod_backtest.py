"""EoD long call butterfly @ King backtest (Pin Play buyer).

Compares long fly @ ``king`` vs ``spot``, optional vs short fly parquet.

Examples:

    python scripts/run_zdte_long_fly_eod_backtest.py --symbol SPY
    python scripts/run_zdte_long_fly_eod_backtest.py --symbol SPY --compare-short
    python scripts/run_zdte_long_fly_eod_backtest.py --min-spot-center-dist 0.15
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from quant_lab.backtest.engine import summarize_returns
from quant_lab.config import settings
from quant_lab.data.storage import list_option_snapshots, load_option_chain, load_underlying
from quant_lab.strategies.zdte_ic_conditional import (
    DEFAULT_PIN_TIER_WEIGHTS,
    PinWeightConfig,
    SizingConfig,
    add_terminal_context,
    contract_weights_from_sizing,
    split_oos_by_cutoff,
    stratified_stats,
    trade_tail_stats,
    weighted_trades_to_daily_returns,
)
from quant_lab.strategies.zdte_ic_eod import (
    DEFAULT_COMMISSION_PER_CONTRACT,
    DEFAULT_WING_WIDTH,
    trades_to_daily_returns,
)
from quant_lab.strategies.zdte_long_fly_eod import CenterMode, simulate_long_fly_trade

log = logging.getLogger(__name__)


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("^", "").replace("/", "_")


def _load_gex(symbol: str) -> pd.DataFrame:
    path = settings.paths.processed / "gex_history" / f"{_safe_symbol(symbol)}.parquet"
    gex = pd.read_parquet(path)
    gex["date"] = pd.to_datetime(gex["date"]).dt.normalize()
    return gex.set_index("date")


def _load_terminal(symbol: str) -> pd.DataFrame:
    path = settings.paths.processed / "terminal" / f"{_safe_symbol(symbol)}.parquet"
    term = pd.read_parquet(path)
    term["date"] = pd.to_datetime(term["date"]).dt.normalize()
    return term.set_index("date")


def _underlying_close_lookup(symbol: str) -> pd.Series:
    bars = load_underlying(symbol, interval="1d")
    close = bars["close"].astype("float64").copy()
    if close.index.tz is not None:
        close.index = close.index.tz_convert(None)
    close.index = close.index.normalize()
    return close[~close.index.duplicated(keep="last")]


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _terminal_field(term: pd.DataFrame, signal_date: str, field: str) -> float:
    ts = pd.Timestamp(signal_date)
    if ts not in term.index:
        return float("nan")
    return float(term.loc[ts, field])


def _enrich_trades_terminal_fields(trades_df: pd.DataFrame, terminal: pd.DataFrame) -> pd.DataFrame:
    term = terminal.reset_index() if "date" not in terminal.columns else terminal.copy()
    term["date"] = pd.to_datetime(term["date"]).dt.normalize()
    term = term.set_index("date")
    out = trades_df.copy()
    out["terminal_regime"] = out["signal_date"].map(
        lambda s: str(term.loc[pd.Timestamp(s), "regime"]) if pd.Timestamp(s) in term.index else "unknown"
    )
    out["pin_score"] = out["signal_date"].map(
        lambda s: float(term.loc[pd.Timestamp(s), "pin_score"]) if pd.Timestamp(s) in term.index else float("nan")
    )
    out["pct_gex_dte1"] = out["signal_date"].map(
        lambda s: float(term.loc[pd.Timestamp(s), "pct_gex_dte1"])
        if pd.Timestamp(s) in term.index
        else float("nan")
    )
    return out


def _simulate_book(
    *,
    symbol: str,
    snapshots: list[str],
    gex: pd.DataFrame,
    terminal: pd.DataFrame,
    close_lookup: pd.Series,
    center_mode: CenterMode,
    regime_filter: str,
    start: date | None,
    end: date | None,
    commission: float,
    min_spot_center_dist_pct: float,
    max_debit_to_wing_ratio: float | None,
) -> tuple[pd.DataFrame, int]:
    n_attempts = 0
    trades: list[dict] = []
    for i in range(1, len(snapshots)):
        signal_date = snapshots[i - 1]
        trade_date = snapshots[i]
        td = date.fromisoformat(trade_date)
        if start is not None and td < start:
            continue
        if end is not None and td > end:
            continue

        ts = pd.Timestamp(signal_date)
        if ts not in gex.index:
            continue
        g_row = gex.loc[ts]
        td_ts = pd.Timestamp(trade_date)
        if td_ts not in close_lookup.index:
            continue
        spot_exit = float(close_lookup.loc[td_ts])

        try:
            chain, meta = load_option_chain(symbol, signal_date)
        except FileNotFoundError:
            continue

        n_attempts += 1
        spot_signal = float(meta["spot"].iloc[0]) if not meta.empty else float(g_row["spot"])
        trade = simulate_long_fly_trade(
            chain,
            signal_date=signal_date,
            trade_date=trade_date,
            spot_signal=spot_signal,
            spot_exit=spot_exit,
            net_gex_bs=float(g_row["net_gex_bs"]),
            center_mode=center_mode,
            king_dte1=_terminal_field(terminal, signal_date, "king_dte1"),
            max_pain_dte1=_terminal_field(terminal, signal_date, "max_pain_dte1"),
            expected_move_1sd=_terminal_field(terminal, signal_date, "expected_move_1sd"),
            regime_filter=regime_filter,  # type: ignore[arg-type]
            commission_per_contract=commission,
            min_spot_center_dist_pct=min_spot_center_dist_pct,
            max_debit_to_wing_ratio=max_debit_to_wing_ratio,
        )
        if trade is None:
            continue
        trades.append(trade.__dict__)

    if not trades:
        return pd.DataFrame(), n_attempts
    return pd.DataFrame(trades), n_attempts


def _apply_sizing_and_stats(
    trades_df: pd.DataFrame,
    terminal: pd.DataFrame,
    *,
    initial_cash: float,
    contracts: int,
    sizing: SizingConfig,
    oos_fraction: float,
    commission: float,
) -> dict[str, object]:
    enriched = add_terminal_context(_enrich_trades_terminal_fields(trades_df, terminal), terminal.reset_index())
    enriched["contracts_sized"] = contract_weights_from_sizing(
        enriched,
        sizing,
        base_contracts=float(contracts),
    )
    enriched["weighted_pnl"] = enriched["pnl_per_contract"] * enriched["contracts_sized"]

    daily_ret = trades_to_daily_returns(enriched, initial_cash=initial_cash, contracts=contracts)
    sized_ret = weighted_trades_to_daily_returns(
        enriched,
        enriched["contracts_sized"],
        initial_cash=initial_cash,
    )
    _, oos_ret, cut = split_oos_by_cutoff(daily_ret, oos_fraction=oos_fraction)
    _, oos_sized, _ = split_oos_by_cutoff(sized_ret, oos_fraction=oos_fraction)
    tail = trade_tail_stats(
        enriched,
        wing_width=DEFAULT_WING_WIDTH,
        commission_per_contract=commission,
    )
    return {
        "enriched": enriched,
        "cut": cut,
        "stats_eq": summarize_returns(daily_ret, initial_cash=initial_cash),
        "stats_oos": summarize_returns(oos_ret, initial_cash=initial_cash),
        "stats_sized": summarize_returns(sized_ret, initial_cash=initial_cash),
        "stats_sized_oos": summarize_returns(oos_sized, initial_cash=initial_cash),
        "tail": tail,
        "oos_n": len(oos_ret),
        "oos_sized_n": len(oos_sized),
    }


def _print_book(label: str, n_attempts: int, stats: dict[str, object], participation: float) -> None:
    enriched: pd.DataFrame = stats["enriched"]  # type: ignore[assignment]
    if enriched.empty:
        print(f"=== {label} ===")
        print(f"  attempts={n_attempts}  filled=0")
        print()
        return
    print(f"=== {label} ===")
    print(f"  attempts={n_attempts}  filled={len(enriched)}  participation={participation:.1%}")
    print(f"  range: {enriched['trade_date'].min()} -> {enriched['trade_date'].max()}")
    print(
        f"  equal-weight ALL Sharpe={stats['stats_eq'].sharpe:.2f}  "  # type: ignore[index]
        f"hit={stats['stats_eq'].hit_rate:.1%}  maxDD={stats['stats_eq'].max_drawdown:.1%}"  # type: ignore[index]
    )
    print(
        f"  equal-weight OOS Sharpe={stats['stats_oos'].sharpe:.2f}  "  # type: ignore[index]
        f"hit={stats['stats_oos'].hit_rate:.1%}  n={stats['oos_n']}"  # type: ignore[index]
    )
    print(
        f"  sized ALL Sharpe={stats['stats_sized'].sharpe:.2f}  "  # type: ignore[index]
        f"total PnL=${enriched['weighted_pnl'].sum():,.0f}"
    )
    print(
        f"  sized OOS Sharpe={stats['stats_sized_oos'].sharpe:.2f}  "  # type: ignore[index]
        f"n={stats['oos_sized_n']}"  # type: ignore[index]
    )
    tail = stats["tail"]
    print(f"  mean PnL=${tail.mean_pnl:.1f}  worst=${tail.worst_pnl:.0f}  CVaR5=${tail.cvar_5pct:.0f}")  # type: ignore[union-attr]
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--regime-filter", choices=("none", "long_gamma_only", "short_gamma_only"), default="none")
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--oos-fraction", type=float, default=0.20)
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument("--commission", type=float, default=DEFAULT_COMMISSION_PER_CONTRACT)
    parser.add_argument(
        "--min-spot-center-dist",
        type=float,
        default=0.0,
        help="min |spot - center| / spot * 100 at signal (0 = no filter)",
    )
    parser.add_argument(
        "--max-debit-wing-ratio",
        type=float,
        default=None,
        help="skip if entry_debit > ratio * wing_width (e.g. 0.5 for cheap flies)",
    )
    parser.add_argument("--compare-short", action="store_true", help="compare to short fly@King parquet")
    parser.add_argument("--weight-pin-high", type=float, default=DEFAULT_PIN_TIER_WEIGHTS["pin_high"])
    parser.add_argument("--weight-pin-mid", type=float, default=DEFAULT_PIN_TIER_WEIGHTS["pin_mid"])
    parser.add_argument("--weight-pin-low", type=float, default=DEFAULT_PIN_TIER_WEIGHTS["pin_low"])
    parser.add_argument("--long-gamma-mult", type=float, default=1.0)
    parser.add_argument("--short-gamma-mult", type=float, default=1.0)
    parser.add_argument("--undetermined-mult", type=float, default=0.75)
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    gex = _load_gex(args.symbol)
    terminal = _load_terminal(args.symbol)
    close_lookup = _underlying_close_lookup(args.symbol)
    snapshots = list_option_snapshots(args.symbol)
    if len(snapshots) < 2:
        print("need at least 2 option snapshots", file=sys.stderr)
        return 1

    sizing = SizingConfig(
        pin=PinWeightConfig(
            w_high=args.weight_pin_high,
            w_mid=args.weight_pin_mid,
            w_low=args.weight_pin_low,
        ),
        long_gamma_mult=args.long_gamma_mult,
        short_gamma_mult=args.short_gamma_mult,
        undetermined_mult=args.undetermined_mult,
    )

    out_dir = settings.paths.processed / "pin_play"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Long call butterfly (buyer): {args.symbol} ===")
    print(
        f"regime_filter={args.regime_filter}  min_spot_center_dist={args.min_spot_center_dist:.2f}%  "
        f"pin sizing={args.weight_pin_high}/{args.weight_pin_mid}/{args.weight_pin_low}"
    )
    print()

    king_df = pd.DataFrame()
    for mode in ("king", "spot"):
        trades_df, n_attempts = _simulate_book(
            symbol=args.symbol,
            snapshots=snapshots,
            gex=gex,
            terminal=terminal,
            close_lookup=close_lookup,
            center_mode=mode,  # type: ignore[arg-type]
            regime_filter=args.regime_filter,
            start=args.start,
            end=args.end,
            commission=args.commission,
            min_spot_center_dist_pct=args.min_spot_center_dist,
            max_debit_to_wing_ratio=args.max_debit_wing_ratio,
        )
        if trades_df.empty:
            _print_book(f"Long fly @ {mode}", n_attempts, {"enriched": pd.DataFrame()}, 0.0)
            continue
        stats = _apply_sizing_and_stats(
            trades_df,
            terminal,
            initial_cash=args.initial_cash,
            contracts=args.contracts,
            sizing=sizing,
            oos_fraction=args.oos_fraction,
            commission=args.commission,
        )
        enriched = stats["enriched"]
        assert isinstance(enriched, pd.DataFrame)
        path = out_dir / f"{_safe_symbol(args.symbol)}_long_fly_{mode}.parquet"
        enriched.to_parquet(path, index=False)
        print(f"wrote {path}")
        if mode == "king":
            king_df = enriched
        _print_book(
            f"Long fly @ {mode}",
            n_attempts,
            stats,
            len(enriched) / max(n_attempts, 1),
        )

    if args.compare_short:
        short_path = out_dir / f"{_safe_symbol(args.symbol)}_pin_fly_king.parquet"
        if short_path.exists() and not king_df.empty:
            short_df = pd.read_parquet(short_path)
            print("--- Long vs short fly @ King (equal-weight total PnL) ---")
            print(f"  long  @King: ${king_df['pnl_per_contract'].sum():,.0f}  ({len(king_df)} trades)")
            print(f"  short @King: ${short_df['pnl_per_contract'].sum():,.0f}  ({len(short_df)} trades)")
            print(f"  long - short: ${king_df['pnl_per_contract'].sum() - short_df['pnl_per_contract'].sum():,.0f}")
            print()

    if not king_df.empty:
        pin_rows = stratified_stats(king_df, king_df["pin_tier"], min_trades=20)
        print("--- long fly @King by pin tier ---")
        for row in pin_rows:
            print(
                f"  {row.label:<14} n={row.n_trades:4d}  Sharpe={row.sharpe:6.2f}  "
                f"hit={row.hit_rate:6.1%}  total=${row.total_pnl:,.0f}"
            )
        print()

    if king_df.empty:
        print("no long fly trades generated", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
