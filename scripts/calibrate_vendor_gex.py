#!/usr/bin/env python3
"""Compare local gamma-flip vs GEXBot vendor zero_gamma (calibration aid)."""

from __future__ import annotations

import argparse
import json
from datetime import date

from quant_lab.data.gexbot_client import get_gexbot_client, gexbot_ticker
from quant_lab.data.vendor_chain import vendor_levels_from_classic
from quant_lab.terminal.live_chain import fetch_intraday_chain
from quant_lab.terminal.snapshot import _row_from_chain


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="^SPX")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today ET)")
    parser.add_argument("--time", default="13:00:00")
    args = parser.parse_args()

    session = date.fromisoformat(args.date) if args.date else date.today()
    chain, spot, time_used, source = fetch_intraday_chain(
        session, args.time, symbol=args.symbol, chain_mode="pin"
    )
    row = _row_from_chain(chain, spot, symbol=args.symbol, asof=session)
    local_flip = float(row.get("flip_dte1", float("nan")))

    client = get_gexbot_client()
    classic = client.classic(gexbot_ticker(args.symbol), "gex_zero")
    vendor = vendor_levels_from_classic(classic)
    vendor_flip = vendor.get("zero_gamma")

    diff_pts = None
    if vendor_flip is not None:
        diff_pts = local_flip - float(vendor_flip)

    out = {
        "symbol": args.symbol,
        "session": session.isoformat(),
        "time_used": time_used,
        "chain_source": source,
        "spot": spot,
        "local_flip_dte1": local_flip,
        "gexbot_zero_gamma": vendor_flip,
        "diff_points": diff_pts,
        "gexbot_majors": vendor,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
