"""Run Phase 3c conditional IC backtest (M3).

**Note:** Skipping trades via pin/regime yields too few samples for 0DTE research.
Prefer ``run_zdte_ic_daily_backtest.py`` (daily participation + stratified pin/regime).

This script compares unconditional long-gamma IC vs a filtered subset for
filter research only.

Examples:

    python scripts/run_zdte_ic_conditional_backtest.py --symbol SPY
    python scripts/run_zdte_ic_conditional_backtest.py --symbol SPY --require-trinity
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
    passes_m3_conditional_filter,
    trade_tail_stats,
)
from quant_lab.strategies.zdte_ic_eod import (
    DEFAULT_COMMISSION_PER_CONTRACT,
    DEFAULT_WING_WIDTH,
    simulate_ic_trade,
    split_is_oos,
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
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df.set_index("date")


def _load_trinity() -> pd.DataFrame:
    path = settings.paths.processed / "trinity" / "history.parquet"
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df.set_index("date")


def _underlying_close_lookup(symbol: str) -> pd.Series:
    bars = load_underlying(symbol, interval="1d")
    close = bars["close"].astype("float64").copy()
    if close.index.tz is not None:
        close.index = close.index.tz_convert(None)
    close.index = close.index.normalize()
    return close[~close.index.duplicated(keep="last")]


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _print_block(
    label: str,
    trades_df: pd.DataFrame,
    *,
    oos_fraction: float,
    initial_cash: float,
    contracts: int,
    wing_width: float,
    commission: float,
) -> tuple[float, float]:
    daily_ret = trades_to_daily_returns(
        trades_df,
        initial_cash=initial_cash,
        contracts=contracts,
    )
    _, oos_ret = split_is_oos(daily_ret, oos_fraction=oos_fraction)
    stats_all = summarize_returns(daily_ret, initial_cash=initial_cash)
    stats_oos = summarize_returns(oos_ret, initial_cash=initial_cash)
    tail = trade_tail_stats(
        trades_df,
        wing_width=wing_width,
        commission_per_contract=commission,
    )

    print(f"=== {label} ({len(trades_df)} trades) ===")
    print(f"  ALL  Sharpe: {stats_all.sharpe:.2f}  hit: {stats_all.hit_rate:.2%}  max DD: {stats_all.max_drawdown:.2%}")
    print(
        f"  OOS  Sharpe: {stats_oos.sharpe:.2f}  hit: {stats_oos.hit_rate:.2%}  "
        f"({len(oos_ret)} days, last {oos_fraction:.0%})"
    )
    print(
        f"  tail worst PnL: ${tail.worst_pnl:,.0f}  "
        f"CVaR 5%: ${tail.cvar_5pct:,.0f}  "
        f"max theoretical loss: ${tail.max_loss_per_trade:,.0f}"
    )
    print()
    return stats_oos.sharpe, stats_oos.hit_rate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--wing-width", type=float, default=DEFAULT_WING_WIDTH)
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--oos-fraction", type=float, default=0.20)
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument("--commission", type=float, default=DEFAULT_COMMISSION_PER_CONTRACT)
    parser.add_argument("--min-pin", type=float, default=70.0)
    parser.add_argument("--min-pct-gex", type=float, default=40.0)
    parser.add_argument(
        "--setup-mode",
        choices=("pin_only", "pin_or_walls", "walls_only"),
        default="pin_only",
    )
    parser.add_argument("--min-trinity", type=float, default=60.0)
    parser.add_argument("--require-trinity", action="store_true")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    try:
        gex = _load_gex(args.symbol)
    except FileNotFoundError as exc:
        print(f"missing gex history: {exc}", file=sys.stderr)
        return 1

    try:
        terminal = _load_terminal(args.symbol)
    except FileNotFoundError as exc:
        print(f"missing terminal history: {exc}", file=sys.stderr)
        return 1

    trinity = _load_trinity()

    try:
        close_lookup = _underlying_close_lookup(args.symbol)
    except FileNotFoundError as exc:
        print(f"underlying missing: {exc}", file=sys.stderr)
        return 2

    snapshots = list_option_snapshots(args.symbol)
    if len(snapshots) < 2:
        print("need at least 2 option snapshots", file=sys.stderr)
        return 1

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
        if ts not in gex.index or ts not in terminal.index:
            continue

        g_row = gex.loc[ts]
        t_row = terminal.loc[ts]
        td_ts = pd.Timestamp(trade_date)
        if td_ts not in close_lookup.index:
            continue
        spot_exit = float(close_lookup.loc[td_ts])

        try:
            chain, meta = load_option_chain(args.symbol, signal_date)
        except FileNotFoundError:
            continue
        spot_signal = float(meta["spot"].iloc[0]) if not meta.empty else float(g_row["spot"])

        trade = simulate_ic_trade(
            chain,
            signal_date=signal_date,
            trade_date=trade_date,
            spot_signal=spot_signal,
            spot_exit=spot_exit,
            net_gex_bs=float(g_row["net_gex_bs"]),
            regime_filter="long_gamma_only",
            wing_width=args.wing_width,
            commission_per_contract=args.commission,
            r=DEFAULT_RISK_FREE_RATE,
            q=DEFAULT_DIVIDEND_YIELD,
        )
        if trade is None:
            continue

        tr_row = trinity.loc[ts] if ts in trinity.index else None
        trinity_score = float(tr_row["trinity_score"]) if tr_row is not None else None
        trinity_direction = (
            str(tr_row["trinity_direction"]) if tr_row is not None else None
        )

        passed, reject_reason = passes_m3_conditional_filter(
            regime=str(t_row["regime"]),
            pin_score=float(t_row["pin_score"]),
            pct_gex_dte1=float(t_row["pct_gex_dte1"]),
            spot=float(t_row["spot"]),
            put_wall=float(t_row["put_wall_dte1"]),
            call_wall=float(t_row["call_wall_dte1"]),
            trinity_score=trinity_score,
            trinity_direction=trinity_direction,
            min_pin=args.min_pin,
            min_trinity=args.min_trinity,
            min_pct_gex_dte1=args.min_pct_gex,
            setup_mode=args.setup_mode,
            require_trinity=args.require_trinity,
        )

        row = trade.__dict__.copy()
        row["terminal_regime"] = str(t_row["regime"])
        row["pin_score"] = float(t_row["pin_score"])
        row["pct_gex_dte1"] = float(t_row["pct_gex_dte1"])
        row["trinity_score"] = trinity_score
        row["trinity_direction"] = trinity_direction
        row["conditional_pass"] = passed
        row["conditional_reason"] = reject_reason
        trades.append(row)

    if not trades:
        print("no trades generated", file=sys.stderr)
        return 3

    trades_df = pd.DataFrame(trades)
    conditional_df = trades_df[trades_df["conditional_pass"]].copy()

    out_dir = settings.paths.processed / "zdte_ic_conditional"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_safe_symbol(args.symbol)}_trades.parquet"
    trades_df.to_parquet(out_path, index=False)

    n_pass = len(conditional_df)
    n_reject = len(trades_df) - n_pass
    reject_counts = trades_df.loc[~trades_df["conditional_pass"], "conditional_reason"].value_counts()

    print(f"=== Phase 3c conditional IC: {args.symbol} ===")
    print(
        f"filter: pin>={args.min_pin}  setup={args.setup_mode}  "
        f"pct_gex>={args.min_pct_gex}  require_trinity={args.require_trinity}"
    )
    print(f"wing={args.wing_width}")
    print(
        f"range: {trades_df['trade_date'].min()} → {trades_df['trade_date'].max()}"
    )
    print(f"unconditional long-gamma trades: {len(trades_df)}")
    print(f"conditional pass: {n_pass}  rejected: {n_reject}")
    if not reject_counts.empty:
        print("reject reasons:", {k: int(v) for k, v in reject_counts.items()})
    print()

    oos_uncond, _ = _print_block(
        "UNCONDITIONAL (3b baseline)",
        trades_df,
        oos_fraction=args.oos_fraction,
        initial_cash=args.initial_cash,
        contracts=args.contracts,
        wing_width=args.wing_width,
        commission=args.commission,
    )
    oos_cond, _ = _print_block(
        "CONDITIONAL (M3 filter)",
        conditional_df,
        oos_fraction=args.oos_fraction,
        initial_cash=args.initial_cash,
        contracts=args.contracts,
        wing_width=args.wing_width,
        commission=args.commission,
    )

    m3_pass = oos_cond > oos_uncond and n_pass >= 30
    print(f"M3 exit (conditional OOS Sharpe > unconditional): {'PASS' if m3_pass else 'FAIL'}")
    print(f"  unconditional OOS Sharpe: {oos_uncond:.2f}")
    print(f"  conditional OOS Sharpe:   {oos_cond:.2f}  (delta {oos_cond - oos_uncond:+.2f})")
    print(f"wrote trades → {out_path}")
    return 0 if m3_pass else 4


if __name__ == "__main__":
    raise SystemExit(main())
