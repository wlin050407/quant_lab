"""Daily-participation EoD IC backtest (Phase 3d).

Attempts an iron condor on **every** signal day with a valid chain — no pin/regime
sit-out filter.  Positioning factors are used for **stratified reporting** only
(higher pin vs lower pin on the same always-in book).

This matches a 0DTE workflow where you trade most sessions; regime/pin adjust
size or structure in live trading, but research needs full sample size.

Examples:

    python scripts/run_zdte_ic_daily_backtest.py --symbol SPY
    python scripts/run_zdte_ic_daily_backtest.py --symbol SPY --regime-filter long_gamma_only
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

import pandas as pd

from quant_lab.backtest.engine import summarize_returns
from quant_lab.config import settings
from quant_lab.data.storage import list_option_snapshots, load_option_chain, load_underlying
from quant_lab.factors.gex import DEFAULT_DIVIDEND_YIELD, DEFAULT_RISK_FREE_RATE
from quant_lab.strategies.zdte_ic_conditional import (
    DEFAULT_PIN_TIER_WEIGHTS,
    DEFAULT_REGIME_MULTIPLIERS,
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
    simulate_ic_trade,
    trades_to_daily_returns,
)

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
    return pd.read_parquet(path)


def _underlying_close_lookup(symbol: str) -> pd.Series:
    bars = load_underlying(symbol, interval="1d")
    close = bars["close"].astype("float64").copy()
    if close.index.tz is not None:
        close.index = close.index.tz_convert(None)
    close.index = close.index.normalize()
    return close[~close.index.duplicated(keep="last")]


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _print_strata(title: str, rows: list) -> None:
    print(f"--- {title} ---")
    if not rows:
        print("  (not enough trades per bucket)")
        return
    for row in rows:
        print(
            f"  {row.label:<14} n={row.n_trades:4d}  "
            f"Sharpe={row.sharpe:6.2f}  hit={row.hit_rate:6.1%}  "
            f"mean_pnl=${row.mean_pnl:7.1f}  total=${row.total_pnl:,.0f}"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument(
        "--regime-filter",
        choices=("none", "long_gamma_only", "short_gamma_only"),
        default="none",
        help="none = daily participation; long_gamma_only = conservative skip short gamma",
    )
    parser.add_argument("--wing-width", type=float, default=DEFAULT_WING_WIDTH)
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--oos-fraction", type=float, default=0.20)
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument("--commission", type=float, default=DEFAULT_COMMISSION_PER_CONTRACT)
    parser.add_argument(
        "--weight-pin-high",
        type=float,
        default=DEFAULT_PIN_TIER_WEIGHTS["pin_high"],
    )
    parser.add_argument(
        "--weight-pin-mid",
        type=float,
        default=DEFAULT_PIN_TIER_WEIGHTS["pin_mid"],
    )
    parser.add_argument(
        "--weight-pin-low",
        type=float,
        default=DEFAULT_PIN_TIER_WEIGHTS["pin_low"],
    )
    parser.add_argument(
        "--long-gamma-mult",
        type=float,
        default=DEFAULT_REGIME_MULTIPLIERS["long_gamma"],
    )
    parser.add_argument(
        "--short-gamma-mult",
        type=float,
        default=DEFAULT_REGIME_MULTIPLIERS["short_gamma"],
    )
    parser.add_argument(
        "--undetermined-mult",
        type=float,
        default=DEFAULT_REGIME_MULTIPLIERS["undetermined"],
    )
    parser.add_argument("--no-pin-weight", action="store_true", help="only show equal-weight book")
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

    n_attempts = 0
    trades: list[dict] = []
    for i in range(1, len(snapshots)):
        signal_date = snapshots[i - 1]
        trade_date = snapshots[i]
        td = date.fromisoformat(trade_date)
        if args.start is not None and td < args.start:
            continue
        if args.end is not None and td > args.end:
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
            chain, meta = load_option_chain(args.symbol, signal_date)
        except FileNotFoundError:
            continue

        n_attempts += 1
        spot_signal = float(meta["spot"].iloc[0]) if not meta.empty else float(g_row["spot"])
        trade = simulate_ic_trade(
            chain,
            signal_date=signal_date,
            trade_date=trade_date,
            spot_signal=spot_signal,
            spot_exit=spot_exit,
            net_gex_bs=float(g_row["net_gex_bs"]),
            regime_filter=args.regime_filter,
            wing_width=args.wing_width,
            commission_per_contract=args.commission,
            r=DEFAULT_RISK_FREE_RATE,
            q=DEFAULT_DIVIDEND_YIELD,
        )
        if trade is None:
            continue
        trades.append(trade.__dict__)

    if not trades:
        print("no trades generated", file=sys.stderr)
        return 3

    trades_df = pd.DataFrame(trades)
    ts = pd.Timestamp(snapshots[0])
    term_rows = terminal.copy()
    term_rows["date"] = pd.to_datetime(term_rows["date"]).dt.normalize()
    term_rows = term_rows.set_index("date")
    trades_df["terminal_regime"] = trades_df["signal_date"].map(
        lambda s: str(term_rows.loc[pd.Timestamp(s), "regime"]) if pd.Timestamp(s) in term_rows.index else "unknown"
    )
    trades_df["pin_score"] = trades_df["signal_date"].map(
        lambda s: float(term_rows.loc[pd.Timestamp(s), "pin_score"]) if pd.Timestamp(s) in term_rows.index else float("nan")
    )
    trades_df["pct_gex_dte1"] = trades_df["signal_date"].map(
        lambda s: float(term_rows.loc[pd.Timestamp(s), "pct_gex_dte1"])
        if pd.Timestamp(s) in term_rows.index
        else float("nan")
    )
    enriched = add_terminal_context(trades_df, terminal)
    enriched["contracts_equal"] = float(args.contracts)

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
    enriched["contracts_sized"] = contract_weights_from_sizing(
        enriched,
        sizing,
        base_contracts=float(args.contracts),
    )
    enriched["weighted_pnl"] = enriched["pnl_per_contract"] * enriched["contracts_sized"]

    daily_ret = trades_to_daily_returns(
        enriched,
        initial_cash=args.initial_cash,
        contracts=args.contracts,
    )
    sized_ret = weighted_trades_to_daily_returns(
        enriched,
        enriched["contracts_sized"],
        initial_cash=args.initial_cash,
    )
    is_ret, oos_ret, cut = split_oos_by_cutoff(daily_ret, oos_fraction=args.oos_fraction)
    stats_all = summarize_returns(daily_ret, initial_cash=args.initial_cash)
    stats_is = summarize_returns(is_ret, initial_cash=args.initial_cash)
    stats_oos = summarize_returns(oos_ret, initial_cash=args.initial_cash)

    is_sized, oos_sized, _ = split_oos_by_cutoff(sized_ret, oos_fraction=args.oos_fraction)
    stats_sized_all = summarize_returns(sized_ret, initial_cash=args.initial_cash)
    stats_sized_is = summarize_returns(is_sized, initial_cash=args.initial_cash)
    stats_sized_oos = summarize_returns(oos_sized, initial_cash=args.initial_cash)
    tail = trade_tail_stats(
        enriched,
        wing_width=args.wing_width,
        commission_per_contract=args.commission,
    )

    out_dir = settings.paths.processed / "zdte_ic_daily"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_safe_symbol(args.symbol)}_trades.parquet"
    enriched.to_parquet(out_path, index=False)

    participation = len(enriched) / max(n_attempts, 1)
    pin_rows = stratified_stats(enriched, enriched["pin_tier"], min_trades=20)
    regime_rows = stratified_stats(enriched, enriched["terminal_regime"], min_trades=20)

    print(f"=== Daily-participation IC: {args.symbol} ===")
    print(f"regime_filter={args.regime_filter}  wing={args.wing_width}")
    print(f"signal days attempted: {n_attempts}  trades filled: {len(enriched)}  "
          f"participation={participation:.1%}")
    print(f"range: {enriched['trade_date'].min()} → {enriched['trade_date'].max()}")
    print()
    print("--- ALL ---")
    print(f"  Sharpe: {stats_all.sharpe:.2f}  hit: {stats_all.hit_rate:.2%}  max DD: {stats_all.max_drawdown:.2%}")
    print(f"  mean PnL/trade: ${tail.mean_pnl:.1f}  worst: ${tail.worst_pnl:.0f}  CVaR 5%: ${tail.cvar_5pct:.0f}")
    print()
    print(f"--- IS (before {cut.date()}) ---")
    print(f"  n={len(is_ret)}  Sharpe={stats_is.sharpe:.2f}  hit={stats_is.hit_rate:.2%}")
    print()
    print(f"--- OOS (from {cut.date()}, calendar split) ---")
    print(f"  n={len(oos_ret)}  Sharpe={stats_oos.sharpe:.2f}  hit={stats_oos.hit_rate:.2%}")
    print()
    if not args.no_pin_weight:
        avg_w = float(enriched["contracts_sized"].mean())
        print("--- Pin × regime sizing (daily participation) ---")
        print(
            f"  pin high/mid/low={args.weight_pin_high}/{args.weight_pin_mid}/{args.weight_pin_low}×  "
            f"regime L/S/U={args.long_gamma_mult}/{args.short_gamma_mult}/{args.undetermined_mult}×"
        )
        print(f"  avg effective contracts/trade: {avg_w:.2f}")
        print(
            f"  ALL  Sharpe={stats_sized_all.sharpe:.2f}  hit={stats_sized_all.hit_rate:.2%}  "
            f"max DD={stats_sized_all.max_drawdown:.2%}"
        )
        print(
            f"  IS   Sharpe={stats_sized_is.sharpe:.2f}  hit={stats_sized_is.hit_rate:.2%}  n={len(is_sized)}"
        )
        print(
            f"  OOS  Sharpe={stats_sized_oos.sharpe:.2f}  hit={stats_sized_oos.hit_rate:.2%}  n={len(oos_sized)}"
        )
        print(
            f"  total weighted PnL: ${enriched['weighted_pnl'].sum():,.0f}  "
            f"vs equal ${(enriched['pnl_per_contract'] * args.contracts).sum():,.0f}"
        )
        print()
    _print_strata("By pin tier (same book, no sit-out)", pin_rows)
    _print_strata("By terminal regime", regime_rows)
    print(f"wrote → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
