"""Daily positioning summary for one stored option-chain snapshot.

Computes GEX, gamma flip, max pain, put-call ratios, and 0DTE OI
concentration from the latest (or specified) snapshot on disk.

Example:

    python scripts/daily_positioning.py --symbol SPY
    python scripts/daily_positioning.py --symbol ^SPX --options-date 2026-05-20
"""

from __future__ import annotations

import argparse
import logging
import sys

import numpy as np

from quant_lab.data.storage import list_option_snapshots, load_option_chain
from quant_lab.factors.gex import (
    DEFAULT_DIVIDEND_YIELD,
    DEFAULT_RISK_FREE_RATE,
    add_bs_gamma_column,
    compute_dealer_gamma_exposure,
    gamma_flip_level,
    net_gex_bn_per_1pct,
    total_net_gex,
)
from quant_lab.factors.positioning import max_pain, oi_concentration, put_call_ratio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--options-date", default=None, help="YYYY-MM-DD; default latest")
    parser.add_argument("--r", type=float, default=DEFAULT_RISK_FREE_RATE)
    parser.add_argument("--q", type=float, default=DEFAULT_DIVIDEND_YIELD)
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    snapshots = list_option_snapshots(args.symbol)
    if not snapshots:
        print(f"no snapshots for {args.symbol}", file=sys.stderr)
        return 1

    options_date = args.options_date or snapshots[-1]
    chain, meta = load_option_chain(args.symbol, options_date)
    spot = float(meta["spot"].iloc[0]) if not meta.empty else float("nan")
    if not np.isfinite(spot) or spot <= 0:
        print(f"invalid spot for {options_date}: {spot}", file=sys.stderr)
        return 2

    with_gamma = add_bs_gamma_column(chain, spot=spot, r=args.r, q=args.q)
    per_strike = compute_dealer_gamma_exposure(with_gamma, spot=spot)
    net_gex = total_net_gex(per_strike)
    flip = gamma_flip_level(with_gamma, spot=spot, r=args.r, q=args.q)

    regime = "LONG GAMMA (vol dampener)" if net_gex > 0 else "SHORT GAMMA (vol amplifier)"
    flip_dist = (spot - flip) / spot * 100 if np.isfinite(flip) else float("nan")

    mp_all = max_pain(chain)
    mp_0dte = max_pain(chain, dte_max=1) if "dte" in chain.columns else float("nan")
    pcr_oi = put_call_ratio(chain, kind="open_interest")
    pcr_vol = put_call_ratio(chain, kind="volume")
    conc_all = oi_concentration(chain, top_n=5)
    conc_0dte = oi_concentration(chain, top_n=5, dte_max=1) if "dte" in chain.columns else float("nan")

    print(f"=== positioning summary: {args.symbol} {options_date} ===")
    print(f"spot:                 {spot:.2f}")
    print(f"net GEX (SpotGamma):    {net_gex_bn_per_1pct(net_gex):+.2f} Bn per 1% move")
    print(f"net GEX (internal):     {net_gex / 1e9:+.2f} Bn per $1 move (Σ Γ×OI×100×S²)")
    print(f"regime:               {regime}")
    print(f"gamma flip:           {flip:.2f}" if np.isfinite(flip) else "gamma flip:           N/A")
    if np.isfinite(flip_dist):
        print(f"spot vs flip:         {flip_dist:+.2f}%")
    print()
    print(f"max pain (all):       {mp_all:.2f}" if np.isfinite(mp_all) else "max pain (all):       N/A")
    print(f"max pain (dte≤1):     {mp_0dte:.2f}" if np.isfinite(mp_0dte) else "max pain (dte≤1):     N/A")
    print(f"put/call OI:          {pcr_oi:.3f}" if np.isfinite(pcr_oi) else "put/call OI:          N/A")
    print(f"put/call volume:      {pcr_vol:.3f}" if np.isfinite(pcr_vol) else "put/call volume:      N/A")
    print(f"top-5 OI conc (all):  {conc_all:.1%}" if np.isfinite(conc_all) else "top-5 OI conc (all):  N/A")
    print(f"top-5 OI conc (dte≤1): {conc_0dte:.1%}" if np.isfinite(conc_0dte) else "top-5 OI conc (dte≤1): N/A")
    print()
    print(f"chain rows:           {len(chain):,}")
    if "dte" in chain.columns:
        print(f"0DTE rows (dte=0):    {int((chain['dte'] == 0).sum()):,}")
        print(f"next-day 0DTE (dte=1): {int((chain['dte'] == 1).sum()):,}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
