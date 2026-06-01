"""Build unified daily terminal factor history (Ultimate Terminal M1).

Combines GEX levels (full chain + dte≤1 cohort), King node, pin score,
expected move, and positioning fields into one parquet per symbol.

Output: ``data/processed/terminal/<symbol>.parquet``

Example:

    python scripts/build_terminal_history.py --symbol SPY
    python scripts/build_terminal_history.py --symbol SPY --skip-flip
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant_lab.config import settings
from quant_lab.data.storage import list_option_snapshots, load_option_chain
from quant_lab.factors.gex import (
    add_bs_gamma_column,
    compute_dealer_gamma_exposure,
    compute_gex_profile,
    compute_vex_profile,
    filter_chain_by_dte,
    max_abs_net_gex_bn,
    net_gex_at_strike,
    net_gex_bn_per_1pct,
    net_vex_bn_per_1pct,
    pct_dte_cohort_of_total,
)
from quant_lab.factors.positioning import (
    atm_iv_from_chain,
    expected_move_1sd,
    max_pain,
    oi_concentration,
    oi_concentration_near_magnet,
    pin_score,
    put_call_ratio,
    resolve_cohort_time_years,
)
from quant_lab.factors.rates import resolve_gex_inputs
from quant_lab.factors.regime import regime_from_net_gex

log = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "date",
    "symbol",
    "spot",
    "regime",
    "net_gex_all",
    "net_gex_dte1",
    "pct_gex_dte1",
    "flip_all",
    "flip_dte1",
    "call_wall_all",
    "put_wall_all",
    "king_all",
    "call_wall_dte1",
    "put_wall_dte1",
    "king_dte1",
    "floor_dte1",
    "ceiling_dte1",
    "max_pain_dte1",
    "pin_score",
    "expected_move_1sd",
    "pcr_oi",
    "oi_conc_dte1",
    "spot_vs_king_pct",
    "spot_vs_flip_pct",
    "n_contracts_all",
    "n_contracts_dte1",
    "net_vex_all",
    "net_vex_dte1",
    "pct_vex_dte1",
    "king_vex_dte1",
    "vanna_interp_dte1",
]


def _output_path(symbol: str) -> Path:
    safe = symbol.replace("^", "").replace("/", "_")
    return settings.paths.processed / "terminal" / f"{safe}.parquet"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _pct_from(spot: float, level: float) -> float:
    if not np.isfinite(spot) or spot <= 0 or not np.isfinite(level):
        return float("nan")
    return float((spot - level) / spot * 100.0)


def compute_terminal_row(
    chain: pd.DataFrame,
    *,
    symbol: str,
    asof: date,
    spot: float,
    compute_flip: bool,
    r: float,
    q: float,
) -> dict[str, float]:
    profile_all = compute_gex_profile(
        chain,
        spot,
        symbol=symbol,
        asof=asof,
        dte_max=None,
        r=r,
        q=q,
        compute_flip=compute_flip,
    )
    profile_dte1 = compute_gex_profile(
        chain,
        spot,
        symbol=symbol,
        asof=asof,
        dte_max=1,
        r=r,
        q=q,
        compute_flip=compute_flip,
    )
    vex_all = compute_vex_profile(chain, spot, symbol=symbol, asof=asof, dte_max=None, r=r, q=q)
    vex_dte1 = compute_vex_profile(chain, spot, symbol=symbol, asof=asof, dte_max=1, r=r, q=q)

    mp_dte1 = max_pain(chain, dte_max=1) if "dte" in chain.columns else float("nan")
    conc_dte1 = (
        oi_concentration(chain, top_n=3, dte_max=1)
        if "dte" in chain.columns
        else float("nan")
    )
    pcr_oi = put_call_ratio(chain, kind="open_interest")
    t_years = resolve_cohort_time_years(chain, dte_max=1)
    iv = atm_iv_from_chain(chain, spot, dte_max=1)
    em = expected_move_1sd(spot, iv, time_years=t_years, dte=1)

    king_for_pin = profile_dte1.king_node if np.isfinite(profile_dte1.king_node) else mp_dte1
    cohort = filter_chain_by_dte(chain, dte_max=1)
    with_gamma = add_bs_gamma_column(
        cohort, spot, symbol=symbol, asof=asof, r=r, q=q
    )
    per_strike = compute_dealer_gamma_exposure(with_gamma, spot)
    magnet_gex_bn = float("nan")
    max_ref = float("nan")
    near_oi = float("nan")
    if np.isfinite(king_for_pin):
        magnet_gex_bn = net_gex_bn_per_1pct(net_gex_at_strike(per_strike, king_for_pin))
        max_ref = max_abs_net_gex_bn(per_strike)
        near_oi = oi_concentration_near_magnet(chain, king_for_pin, spot, dte_max=1)

    regime = regime_from_net_gex(profile_dte1.net_gex)
    pct_dte = pct_dte_cohort_of_total(profile_dte1.net_gex, profile_all.net_gex)
    pct_vex = pct_dte_cohort_of_total(vex_dte1.net_vex, vex_all.net_vex)

    ps = pin_score(
        spot=spot,
        magnet_strike=king_for_pin,
        oi_concentration_top3=conc_dte1 if np.isfinite(conc_dte1) else 0.0,
        magnet_gex_bn_per_1pct=magnet_gex_bn,
        time_to_close_pct=100.0,
        expected_move_1sd=em,
        max_gex_bn_reference=max_ref,
        max_pain_strike=mp_dte1,
        pct_gex_dte1=pct_dte,
        oi_near_magnet=near_oi,
    )

    return {
        "spot": float(spot),
        "regime": regime,
        "net_gex_all": profile_all.net_gex,
        "net_gex_dte1": profile_dte1.net_gex,
        "pct_gex_dte1": pct_dte,
        "flip_all": profile_all.flip_level,
        "flip_dte1": profile_dte1.flip_level,
        "call_wall_all": profile_all.call_wall,
        "put_wall_all": profile_all.put_wall,
        "king_all": profile_all.king_node,
        "call_wall_dte1": profile_dte1.call_wall,
        "put_wall_dte1": profile_dte1.put_wall,
        "king_dte1": profile_dte1.king_node,
        "floor_dte1": profile_dte1.floor_strike,
        "ceiling_dte1": profile_dte1.ceiling_strike,
        "max_pain_dte1": float(mp_dte1),
        "pin_score": ps,
        "expected_move_1sd": em,
        "pcr_oi": float(pcr_oi),
        "oi_conc_dte1": float(conc_dte1),
        "spot_vs_king_pct": _pct_from(spot, profile_dte1.king_node),
        "spot_vs_flip_pct": _pct_from(spot, profile_dte1.flip_level),
        "n_contracts_all": float(profile_all.n_contracts),
        "n_contracts_dte1": float(profile_dte1.n_contracts),
        "net_vex_all": vex_all.net_vex,
        "net_vex_dte1": vex_dte1.net_vex,
        "pct_vex_dte1": pct_vex,
        "king_vex_dte1": vex_dte1.king_node,
        "vanna_interp_dte1": vex_dte1.interpretation,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--skip-flip", action="store_true")
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    out_path = _output_path(args.symbol)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing = pd.DataFrame(columns=OUTPUT_COLUMNS)
    if out_path.exists() and not args.rebuild:
        existing = pd.read_parquet(out_path)

    snapshots = list_option_snapshots(args.symbol)
    if not snapshots:
        print(f"no snapshots for {args.symbol}", file=sys.stderr)
        return 1

    candidates = [
        date.fromisoformat(s)
        for s in snapshots
        if (args.start is None or date.fromisoformat(s) >= args.start)
        and (args.end is None or date.fromisoformat(s) <= args.end)
    ]
    existing_dates = (
        set(pd.to_datetime(existing["date"]).dt.date) if not existing.empty else set()
    )
    todo = candidates if args.rebuild else [d for d in candidates if d not in existing_dates]
    log.info("symbol=%s todo=%d", args.symbol, len(todo))

    rows: list[dict] = []
    start_ts = time.monotonic()
    for i, d in enumerate(todo, start=1):
        chain, meta = load_option_chain(args.symbol, d.isoformat())
        spot = float(meta["spot"].iloc[0]) if not meta.empty else float("nan")
        if not np.isfinite(spot) or spot <= 0:
            continue
        gex_inp = resolve_gex_inputs(args.symbol, asof=d)
        row = compute_terminal_row(
            chain,
            symbol=args.symbol,
            asof=d,
            spot=spot,
            compute_flip=not args.skip_flip,
            r=gex_inp.r,
            q=gex_inp.q,
        )
        row["date"] = pd.Timestamp(d)
        row["symbol"] = args.symbol
        rows.append(row)
        if i % args.progress_every == 0 or i == len(todo):
            elapsed = time.monotonic() - start_ts
            log.info("[%d/%d] %s (%.0f snap/s)", i, len(todo), d, i / max(elapsed, 1e-9))

    if not rows:
        print("nothing new to compute")
        return 0

    new_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    combined = pd.concat([existing, new_df], ignore_index=True) if not args.rebuild else new_df
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    combined.to_parquet(out_path, engine="pyarrow")
    print(f"wrote {len(combined)} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
