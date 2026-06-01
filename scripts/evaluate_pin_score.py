"""Evaluate pin / magnet prediction quality vs realized close proximity.

Runs Phase 3e-style IC + stratum tests and adds within-EM hit rates by pin tier.
Rebuild terminal history after pin engine changes:

    python scripts/build_terminal_history.py --symbol SPY --rebuild
    python scripts/evaluate_pin_score.py --symbol SPY
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant_lab.config import settings
from quant_lab.data.storage import load_underlying
from quant_lab.factors.pin_king_proximity import (
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


def _within_em_rate(frame: pd.DataFrame) -> pd.DataFrame:
    """Fraction of days with |close−magnet| <= expected_move, by pin tier."""
    if frame.empty or "expected_move_1sd" not in frame.columns:
        return pd.DataFrame()

    work = frame.loc[frame["valid"]].copy() if "valid" in frame.columns else frame.copy()
    em = work["expected_move_1sd"].astype("float64")
    work["within_em"] = work["abs_dist_pts"] <= em
    rows: list[dict[str, float | str | int]] = []
    for tier, grp in work.groupby("pin_tier", observed=True):
        n = len(grp)
        hit = int(grp["within_em"].sum()) if n else 0
        rows.append(
            {
                "pin_tier": str(tier),
                "n": n,
                "within_em_n": hit,
                "within_em_rate": float(hit / n) if n else float("nan"),
                "median_abs_dist_pct": float(grp["abs_dist_pct"].median()) if n else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate pin score vs magnet proximity.")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--mode", choices=("same_day", "next_session"), default="same_day")
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--export", action="store_true", help="Write CSV summaries under processed/pin_play/")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    term = _load_terminal(args.symbol, args.start, args.end)
    und = load_underlying(args.symbol)
    frame = build_proximity_frame(term, und, mode=args.mode)
    if frame.empty:
        log.error("empty proximity frame — check terminal + underlying overlap")
        return 1

    ic, ic_n = proximity_ic(frame)
    comp = compare_pin_strata(frame, mode=args.mode)
    gate = evaluate_phase3e_gate(frame, mode=args.mode)
    strata = summarize_by_stratum(frame)
    em_table = _within_em_rate(frame)

    print(f"=== Pin evaluation: {args.symbol} mode={args.mode} n={len(frame)} ===")
    print(f"Spearman IC (pin vs -|dist|): {ic:+.3f}  n={ic_n}")
    print()
    print(
        f"High pin (≥70): median |dist|={comp.high_median_abs_dist_pct:.3f}%  n={comp.high_n}"
    )
    print(
        f"Low pin (<50):  median |dist|={comp.low_median_abs_dist_pct:.3f}%  n={comp.low_n}"
    )
    print(f"Mann-Whitney p={comp.p_value:.4g}  median test={'PASS' if comp.passes_median_test else 'FAIL'}")
    print()
    print(f"Phase 3e gate: {'PASS' if gate.passes else 'FAIL'}  (high-pin long-γ n={gate.high_pin_long_gamma_n})")
    print()
    if not strata.empty:
        print("=== By pin tier ===")
        print(strata.to_string(index=False))
        print()
    if not em_table.empty:
        print("=== Within expected move (1σ) ===")
        print(em_table.to_string(index=False))
        print()

    if args.export:
        out_dir = settings.paths.processed / "pin_play"
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = _safe_symbol(args.symbol)
        frame.to_csv(out_dir / f"pin_eval_{tag}_{args.mode}.csv", index=False)
        strata.to_csv(out_dir / f"pin_eval_strata_{tag}_{args.mode}.csv", index=False)
        em_table.to_csv(out_dir / f"pin_eval_within_em_{tag}_{args.mode}.csv", index=False)
        log.info("wrote CSVs under %s", out_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
