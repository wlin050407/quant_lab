"""Phase 4 — intraday Pin Play iron butterfly @ King (ThetaData SPXW).

Examples:

    python scripts/run_zdte_pin_fly_intraday_backtest.py
    python scripts/run_zdte_pin_fly_intraday_backtest.py --start 2023-01-03 --end 2024-12-31
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

import pandas as pd

from quant_lab.backtest.engine import summarize_returns
from quant_lab.config import settings
from quant_lab.data.thetadata_chain import load_built_intraday_chain, list_intraday_chain_dates
from quant_lab.strategies.zdte_ic_conditional import (
    PinWeightConfig,
    SizingConfig,
    contract_weights_from_sizing,
    pin_tier,
    split_oos_by_cutoff,
    stratified_stats,
    trade_tail_stats,
    weighted_trades_to_daily_returns,
)
from quant_lab.strategies.zdte_ic_eod import DEFAULT_COMMISSION_PER_CONTRACT, trades_to_daily_returns
from quant_lab.strategies.zdte_pin_fly_eod import CenterMode, wing_width_from_expected_move
from quant_lab.strategies.zdte_pin_fly_intraday import (
    DEFAULT_ENTRY_TIME,
    DEFAULT_EXIT_TIME,
    simulate_pin_fly_intraday_session,
)

log = logging.getLogger(__name__)

PIN_PLAY_PIN_WEIGHTS = {"pin_high": 1.0, "pin_mid": 0.5, "pin_low": 0.25, "pin_unknown": 0.25}


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _sessions_with_chains(
    *,
    entry_time: str,
    exit_time: str,
    start: date | None,
    end: date | None,
) -> list[date]:
    out: list[date] = []
    for iso in list_intraday_chain_dates():
        session = date.fromisoformat(iso)
        if start is not None and session < start:
            continue
        if end is not None and session > end:
            continue
        try:
            load_built_intraday_chain(session, entry_time)
            load_built_intraday_chain(session, exit_time)
        except FileNotFoundError:
            continue
        out.append(session)
    return sorted(out)


def _simulate_book(
    sessions: list[date],
    *,
    entry_time: str,
    exit_time: str,
    commission: float,
    require_long_gamma: bool,
    center_mode: CenterMode = "king",
    fusion_gate: bool = True,
) -> tuple[pd.DataFrame, int]:
    trades: list[dict] = []
    for session in sessions:
        try:
            chain_entry, meta_entry = load_built_intraday_chain(session, entry_time)
            chain_exit, _meta_exit = load_built_intraday_chain(session, exit_time)
        except FileNotFoundError:
            continue

        spot_entry = float("nan")
        if not meta_entry.empty and "spot" in meta_entry.columns:
            spot_entry = float(meta_entry["spot"].iloc[0])
        if not pd.notna(spot_entry):
            continue

        trade = simulate_pin_fly_intraday_session(
            chain_entry,
            session_date=session,
            spot_entry=spot_entry,
            chain_exit=chain_exit,
            entry_time=entry_time,
            exit_time=exit_time,
            commission_per_contract=commission,
            require_long_gamma=require_long_gamma,
            center_mode=center_mode,
            fusion_gate=fusion_gate,
        )
        if trade is None:
            continue
        row = trade.__dict__.copy()
        row["trade_date"] = row.pop("session_date")
        row["signal_date"] = row["trade_date"]
        trades.append(row)

    return pd.DataFrame(trades), len(sessions)


def _enrich_for_sizing(trades_df: pd.DataFrame) -> pd.DataFrame:
    out = trades_df.copy()
    out["terminal_regime"] = out["regime"].astype(str)
    out["pin_tier"] = out["pin_score"].map(pin_tier)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=_parse_date, default=date(2023, 1, 3))
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--entry-time", default=DEFAULT_ENTRY_TIME)
    parser.add_argument("--exit-time", default=DEFAULT_EXIT_TIME)
    parser.add_argument("--oos-fraction", type=float, default=0.20)
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument("--commission", type=float, default=DEFAULT_COMMISSION_PER_CONTRACT)
    parser.add_argument(
        "--allow-short-gamma",
        action="store_true",
        help="include short_gamma entries (default: skip per Pin Play spec)",
    )
    parser.add_argument(
        "--center",
        choices=("king", "fused", "compare"),
        default="compare",
        help="fly body strike: king, fused pin_center, or compare both",
    )
    parser.add_argument(
        "--no-fusion-gate",
        action="store_true",
        help="fused mode: do not skip on pin_center entry_blocked (sensitivity)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    sessions = _sessions_with_chains(
        entry_time=args.entry_time,
        exit_time=args.exit_time,
        start=args.start,
        end=args.end,
    )
    if not sessions:
        print("no sessions with entry+exit intraday chains", file=sys.stderr)
        return 1

    modes: tuple[CenterMode, ...]
    if args.center == "compare":
        modes = ("king", "fused")
    else:
        modes = (args.center,)  # type: ignore[assignment]

    all_results: dict[str, pd.DataFrame] = {}
    attempts_by_mode: dict[str, int] = {}
    for mode in modes:
        trades_df, n_sessions = _simulate_book(
            sessions,
            entry_time=args.entry_time,
            exit_time=args.exit_time,
            commission=args.commission,
            require_long_gamma=not args.allow_short_gamma,
            center_mode=mode,
            fusion_gate=not args.no_fusion_gate,
        )
        attempts_by_mode[mode] = n_sessions
        all_results[mode] = trades_df

    if args.center != "compare":
        trades_df = all_results.get(args.center, pd.DataFrame())
        n_sessions = attempts_by_mode.get(args.center, 0)
        if trades_df.empty:
            print(f"sessions={n_sessions} but no trades filled (center={args.center})", file=sys.stderr)
            return 2
        _run_single_report(
            trades_df,
            n_sessions,
            args,
            label=f"Pin Play intraday iron fly @ {args.center} (SPXW)",
            out_name=f"SPX_pin_fly_intraday_{args.center}.parquet",
        )
        return 0

    king_df = all_results.get("king", pd.DataFrame())
    fused_df = all_results.get("fused", pd.DataFrame())
    n_sessions = attempts_by_mode.get("king", 0)
    if king_df.empty and fused_df.empty:
        print(f"sessions={n_sessions} but no trades filled", file=sys.stderr)
        return 2

    print("=== Pin Play intraday iron fly: King vs fused (SPXW) ===")
    print()
    for mode, df in (("king", king_df), ("fused", fused_df)):
        if df.empty:
            print(f"--- @ {mode}: no trades ---")
            print()
            continue
        _run_single_report(
            df,
            n_sessions,
            args,
            label=f"Iron fly @ {mode}",
            out_name=f"SPX_pin_fly_intraday_{mode}.parquet",
            compact=True,
        )
    if not king_df.empty and not fused_df.empty:
        k = float(king_df["pnl_per_contract"].sum())
        f = float(fused_df["pnl_per_contract"].sum())
        print("--- structure compare (equal-weight total PnL) ---")
        print(f"  @King:  ${k:,.0f}  ({len(king_df)} trades)")
        print(f"  @fused: ${f:,.0f}  ({len(fused_df)} trades)")
        print(f"  fused - King: ${f - k:,.0f}")
        print()
    return 0


def _run_single_report(
    trades_df: pd.DataFrame,
    n_sessions: int,
    args: argparse.Namespace,
    *,
    label: str,
    out_name: str,
    compact: bool = False,
) -> None:
    sizing = SizingConfig(
        pin=PinWeightConfig(
            w_high=PIN_PLAY_PIN_WEIGHTS["pin_high"],
            w_mid=PIN_PLAY_PIN_WEIGHTS["pin_mid"],
            w_low=PIN_PLAY_PIN_WEIGHTS["pin_low"],
        ),
        long_gamma_mult=1.0,
        short_gamma_mult=0.0,
        undetermined_mult=0.75,
    )
    enriched = _enrich_for_sizing(trades_df)
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
    _, oos_ret, cut = split_oos_by_cutoff(daily_ret, oos_fraction=args.oos_fraction)
    _, oos_sized, _ = split_oos_by_cutoff(sized_ret, oos_fraction=args.oos_fraction)

    stats_eq = summarize_returns(daily_ret, initial_cash=args.initial_cash)
    stats_oos = summarize_returns(oos_ret, initial_cash=args.initial_cash)
    stats_sized = summarize_returns(sized_ret, initial_cash=args.initial_cash)
    stats_sized_oos = summarize_returns(oos_sized, initial_cash=args.initial_cash)
    tail = trade_tail_stats(
        enriched,
        wing_width=wing_width_from_expected_move(25.0, spx_notional=True),
        commission_per_contract=args.commission,
    )

    out_dir = settings.paths.processed / "pin_play"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / out_name
    enriched.to_parquet(out_path, index=False)

    participation = len(enriched) / max(n_sessions, 1)
    print(f"=== {label} ===")
    print(f"sessions={n_sessions}  filled={len(enriched)}  participation={participation:.1%}")
    print(f"range: {enriched['trade_date'].min()} -> {enriched['trade_date'].max()}")
    print(f"wrote {out_path}")
    print()
    print(
        f"equal-weight ALL Sharpe={stats_eq.sharpe:.2f}  hit={stats_eq.hit_rate:.1%}  "
        f"total PnL=${enriched['pnl_per_contract'].sum():,.0f}"
    )
    print(
        f"equal-weight OOS Sharpe={stats_oos.sharpe:.2f}  hit={stats_oos.hit_rate:.1%}  "
        f"n={len(oos_ret)}  (from {cut.date()})"
    )
    print(
        f"sized ALL Sharpe={stats_sized.sharpe:.2f}  hit={stats_sized.hit_rate:.1%}  "
        f"total PnL=${enriched['weighted_pnl'].sum():,.0f}"
    )
    print(
        f"sized OOS Sharpe={stats_sized_oos.sharpe:.2f}  hit={stats_sized_oos.hit_rate:.1%}  "
        f"n={len(oos_sized)}"
    )
    print(f"mean PnL=${tail.mean_pnl:.1f}  worst=${tail.worst_pnl:.0f}  CVaR5=${tail.cvar_5pct:.0f}")
    print()

    if not compact:
        exit_counts = enriched["exit_reason"].value_counts()
        print("--- exit reasons ---")
        for reason, count in exit_counts.items():
            print(f"  {reason}: {count}")
        print()

        pin_rows = stratified_stats(enriched, enriched["pin_tier"], min_trades=10)
        print("--- by pin tier ---")
        for row in pin_rows:
            print(
                f"  {row.label:<14} n={row.n_trades:4d}  Sharpe={row.sharpe:6.2f}  "
                f"hit={row.hit_rate:6.1%}  total=${row.total_pnl:,.0f}"
            )
        print()

        gate = stats_sized_oos.sharpe > 0.8
        print(f"Phase 4 gate (sized OOS Sharpe > 0.8): {'PASS' if gate else 'FAIL'} ({stats_sized_oos.sharpe:.2f})")
        print()


if __name__ == "__main__":
    raise SystemExit(main())
