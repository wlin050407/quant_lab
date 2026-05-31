"""Run SpotGamma calibration checks against config/spotgamma_reference.yaml.

Examples:

    python scripts/calibrate_spotgamma.py
    python scripts/calibrate_spotgamma.py --date 2024-08-05
    python scripts/calibrate_spotgamma.py --tolerance-pct 0.30
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from quant_lab.data.storage import load_option_chain
from quant_lab.factors.calibration import (
    check_against_reference,
    compute_gex_snapshot,
    load_reference,
)

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference",
        type=Path,
        default=None,
        help="path to spotgamma_reference.yaml (default: config/spotgamma_reference.yaml)",
    )
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--date", default=None, help="run one date only")
    parser.add_argument(
        "--tolerance-pct",
        type=float,
        default=0.30,
        help="allowed relative error for magnitude fields (default 30%%)",
    )
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    refs = load_reference(args.reference)
    if args.date is not None:
        refs = [r for r in refs if r.get("date") == args.date]
        if not refs:
            print(f"no reference entry for date {args.date}", file=sys.stderr)
            return 1

    n_pass = 0
    n_fail = 0
    print(f"SpotGamma calibration — {args.symbol} (tolerance ±{args.tolerance_pct:.0%})")
    print()

    for ref in refs:
        asof = str(ref["date"])
        try:
            chain, meta = load_option_chain(args.symbol, asof)
        except FileNotFoundError:
            print(f"[SKIP] {asof}: no snapshot on disk")
            continue

        spot = float(meta["spot"].iloc[0]) if not meta.empty else float("nan")
        snap = compute_gex_snapshot(chain, spot=spot, asof_date=asof)
        result = check_against_reference(
            snap, ref, tolerance_pct=args.tolerance_pct
        )

        status = "PASS" if result.passed else "FAIL"
        if result.passed:
            n_pass += 1
        else:
            n_fail += 1

        print(f"--- {asof} [{status}] ---")
        print(f"source: {ref.get('source', 'n/a')}")
        print(f"spot={snap.spot:.2f}  net_gex={snap.net_gex_bn_per_1pct:+.2f} Bn/1%  "
              f"flip={snap.flip_level:.2f}  regime={snap.regime}")
        print(f"call_wall={snap.call_wall_strike:.0f}  put_wall={snap.put_wall_strike:.0f}")
        for msg in result.messages:
            print(f"  {msg}")
        print()

    print(f"summary: {n_pass} passed, {n_fail} failed, {len(refs) - n_pass - n_fail} skipped")
    return 0 if n_fail == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
