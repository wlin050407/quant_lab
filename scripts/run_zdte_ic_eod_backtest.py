"""Run EoD-approximate 0DTE iron condor simulation (Phase 3b).

Examples:

    python scripts/run_zdte_ic_eod_backtest.py --symbol SPY
    python scripts/run_zdte_ic_eod_backtest.py --symbol SPY --regime-filter none
    python scripts/run_zdte_ic_eod_backtest.py --symbol SPY --wing-width 3
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
from quant_lab.factors.ic import spearman_ic
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


def _underlying_close_lookup(symbol: str) -> pd.Series:
    bars = load_underlying(symbol, interval="1d")
    close = bars["close"].astype("float64").copy()
    if close.index.tz is not None:
        close.index = close.index.tz_convert(None)
    close.index = close.index.normalize()
    return close[~close.index.duplicated(keep="last")]


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument(
        "--regime-filter",
        choices=("long_gamma_only", "short_gamma_only", "none"),
        default="long_gamma_only",
    )
    parser.add_argument("--wing-width", type=float, default=DEFAULT_WING_WIDTH)
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--oos-fraction", type=float, default=0.20)
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument(
        "--commission",
        type=float,
        default=DEFAULT_COMMISSION_PER_CONTRACT,
    )
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    try:
        gex = _load_gex(args.symbol)
    except FileNotFoundError as exc:
        print(f"missing processed history: {exc}", file=sys.stderr)
        return 1

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
        print("no trades generated — check regime filter / dte=1 availability", file=sys.stderr)
        return 3

    trades_df = pd.DataFrame(trades)
    daily_ret = trades_to_daily_returns(
        trades_df,
        initial_cash=args.initial_cash,
        contracts=args.contracts,
    )
    is_ret, oos_ret = split_is_oos(daily_ret, oos_fraction=args.oos_fraction)

    stats_all = summarize_returns(daily_ret, initial_cash=args.initial_cash)
    stats_is = summarize_returns(is_ret, initial_cash=args.initial_cash)
    stats_oos = summarize_returns(oos_ret, initial_cash=args.initial_cash)

    merged = trades_df.copy()
    close_sorted = close_lookup.sort_index()
    abs_ret = close_sorted.pct_change().abs()
    merged["trade_ts"] = pd.to_datetime(merged["trade_date"])
    merged["abs_day_return"] = merged["trade_ts"].map(
        lambda d: float(abs_ret.loc[d]) if d in abs_ret.index else float("nan")
    )
    ic, ic_n = spearman_ic(
        merged["net_gex_bs"].astype("float64"),
        merged["abs_day_return"],
    )

    out_dir = settings.paths.processed / "zdte_ic_eod"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_safe_symbol(args.symbol)}_trades.parquet"
    trades_df.to_parquet(out_path, index=False)

    n_walls = int((trades_df["strike_source"] == "walls").sum())
    n_em = int((trades_df["strike_source"] == "expected_move").sum())

    print(f"=== 0DTE IC EoD simulation: {args.symbol} ===")
    print(f"regime={args.regime_filter}  wing={args.wing_width}  commission={args.commission}")
    print(
        f"trades: {len(trades_df)}  range: {trades_df['trade_date'].min()} → {trades_df['trade_date'].max()}"
    )
    print(f"strike source: walls={n_walls}  expected_move={n_em}")
    print()
    print("--- ALL ---")
    print(f"  total return: {stats_all.total_return:+.2%}")
    print(f"  Sharpe:       {stats_all.sharpe:.2f}")
    print(f"  hit rate:     {stats_all.hit_rate:.2%}")
    print(f"  max DD:       {stats_all.max_drawdown:.2%}")
    print()
    print(f"--- IS ({len(is_ret)} trade-days) ---")
    print(f"  Sharpe: {stats_is.sharpe:.2f}  hit rate: {stats_is.hit_rate:.2%}")
    print()
    print(f"--- OOS ({len(oos_ret)} trade-days, last {args.oos_fraction:.0%}) ---")
    print(f"  Sharpe: {stats_oos.sharpe:.2f}  hit rate: {stats_oos.hit_rate:.2%}")
    print()
    print(f"net_gex IC vs same-day |return|: {ic:+.4f}  n={ic_n}")
    print()
    gate_pass = stats_oos.sharpe > 0.5 and stats_oos.hit_rate > 0.52
    print(f"Phase 3 gate (OOS Sharpe>0.5 & hit>52%): {'PASS' if gate_pass else 'FAIL'}")
    print(f"wrote trades → {out_path}")
    return 0 if gate_pass else 4


if __name__ == "__main__":
    raise SystemExit(main())
