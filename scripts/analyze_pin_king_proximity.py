"""Phase 3e — Pin score vs King proximity analysis.

Validates whether high-pin + long-gamma days see close land nearer ``king_dte1``
than low-pin days.  See ``docs/PIN_PLAY_SPEC.md``.

Examples:

    python scripts/analyze_pin_king_proximity.py --symbol SPY
    python scripts/analyze_pin_king_proximity.py --symbol SPY --mode same_day --export
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from quant_lab.config import settings
from quant_lab.data.storage import load_underlying
from quant_lab.factors.pin_king_proximity import (
    ProximityMode,
    build_proximity_frame,
    compare_pin_strata,
    evaluate_phase3e_gate,
    proximity_ic,
    summarize_by_stratum,
)

log = logging.getLogger(__name__)


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("^", "").replace("/", "_")


def _terminal_path(symbol: str) -> Path:
    return settings.paths.processed / "terminal" / f"{_safe_symbol(symbol)}.parquet"


def _output_dir() -> Path:
    return settings.paths.processed / "pin_play"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _load_terminal(symbol: str, start: date | None, end: date | None) -> pd.DataFrame:
    path = _terminal_path(symbol)
    if not path.exists():
        raise FileNotFoundError(
            f"terminal parquet missing: {path}. Run: python scripts/build_terminal_history.py"
        )
    term = pd.read_parquet(path)
    term["date"] = pd.to_datetime(term["date"]).dt.normalize()
    if start is not None:
        term = term[term["date"].dt.date >= start]
    if end is not None:
        term = term[term["date"].dt.date <= end]
    return term.reset_index(drop=True)


def _print_comparison(title: str, comp) -> None:
    print(f"=== {title} ===")
    print(f"  high: {comp.high_label}  n={comp.high_n}  median |dist|={comp.high_median_abs_dist_pct:.3f}%")
    print(f"  low:  {comp.low_label}   n={comp.low_n}  median |dist|={comp.low_median_abs_dist_pct:.3f}%")
    print(f"  Mann-Whitney U={comp.u_statistic:.1f}  p={comp.p_value:.4g}  alt={comp.alternative}")
    print(f"  median test: {'PASS' if comp.passes_median_test else 'FAIL'}")
    print()


def _print_strata(title: str, table: pd.DataFrame) -> None:
    print(f"=== {title} ===")
    if table.empty:
        print("  (empty)")
        print()
        return
    for _, row in table.iterrows():
        print(
            f"  pin={row['pin_tier']:<7} regime={str(row['regime']):<14} "
            f"n={int(row['n']):>4}  median_dist={row['median_abs_dist_pct']:>6.3f}%  "
            f"within_em={row['within_em_rate'] * 100:>5.1f}%"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument(
        "--mode",
        choices=["same_day", "next_session", "both"],
        default="both",
        help="same_day=EOD spot vs King; next_session=signal t → close t+1 vs King_t",
    )
    parser.add_argument("--export", action="store_true", help="write parquet to data/processed/pin_play/")
    parser.add_argument("--min-high-n", type=int, default=200, help="Phase 3e sample gate for pin>=70 long_gamma")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    terminal = _load_terminal(args.symbol, args.start, args.end)
    underlying = load_underlying(args.symbol, interval="1d")

    modes: list[ProximityMode]
    if args.mode == "both":
        modes = ["same_day", "next_session"]
    else:
        modes = [args.mode]  # type: ignore[list-item]

    out_dir = _output_dir()
    if args.export:
        out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Pin Play Phase 3e - King proximity ({args.symbol})")
    print(f"terminal rows: {len(terminal)}")
    print()

    gate_pass_any = False
    for mode in modes:
        frame = build_proximity_frame(terminal, underlying, mode=mode)
        valid_n = int(frame["valid"].sum())
        print(f"--- mode={mode}  valid_rows={valid_n} ---")

        strata = summarize_by_stratum(frame)
        _print_strata(f"Strata ({mode})", strata)

        ic, ic_n = proximity_ic(frame)
        print(f"Spearman IC pin_score vs -|dist|: {ic:+.4f}  n={ic_n}")
        print()

        _print_comparison(
            f"Primary: pin>=70 + long_gamma vs pin<50 ({mode})",
            compare_pin_strata(frame, mode=mode, regime="long_gamma"),
        )
        _print_comparison(
            f"Secondary: pin>=70 (all regimes) vs pin<50 ({mode})",
            compare_pin_strata(frame, mode=mode, regime=None),
        )

        gate = evaluate_phase3e_gate(
            frame,
            mode=mode,
            min_high_pin_long_gamma_n=args.min_high_n,
        )
        print(f"Phase 3e gate ({mode}):")
        print(f"  pin>=70 long_gamma n={gate.high_pin_long_gamma_n} (need >={gate.min_high_pin_long_gamma_n})")
        print(f"  sample gate: {'PASS' if gate.passes_sample_size else 'FAIL'}")
        print(f"  full gate:   {'PASS' if gate.passes else 'FAIL'}")
        print()

        if gate.passes:
            gate_pass_any = True

        if args.export:
            out_path = out_dir / f"{_safe_symbol(args.symbol)}_king_proximity_{mode}.parquet"
            export_cols = [
                "date",
                "symbol",
                "mode",
                "valid",
                "spot",
                "king_dte1",
                "pin_score",
                "pin_tier",
                "regime",
                "expected_move_1sd",
                "outcome_close",
                "abs_dist_pts",
                "abs_dist_pct",
                "signed_dist_pct",
                "within_em",
                "within_half_em",
                "n_contracts_dte1",
                "pct_gex_dte1",
            ]
            cols = [c for c in export_cols if c in frame.columns]
            frame[cols].to_parquet(out_path, engine="pyarrow")
            print(f"wrote {out_path}")
            print()

    return 0 if gate_pass_any or args.mode != "both" else 0


if __name__ == "__main__":
    raise SystemExit(main())
