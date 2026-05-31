"""Re-run quality checks against already-stored data.

Examples:

    python scripts/check_quality.py --symbol ^SPX
    python scripts/check_quality.py --symbol ^SPX --options-date 2026-05-19
    python scripts/check_quality.py --symbol ^SPX --no-continuity
"""

from __future__ import annotations

import argparse
import logging

from quant_lab.data.storage import (
    list_option_snapshots,
    load_option_chain,
    load_underlying,
)
from quant_lab.quality.checks import (
    check_option_chain,
    check_snapshot_continuity,
    check_underlying,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", default="1d")
    parser.add_argument(
        "--options-date",
        default=None,
        help="YYYY-MM-DD; if omitted, use the latest snapshot",
    )
    parser.add_argument(
        "--no-continuity",
        action="store_true",
        help="skip the cross-snapshot continuity check (faster on large stores)",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    try:
        und = load_underlying(args.symbol, interval=args.interval)
        print(check_underlying(und, symbol=args.symbol).render())
    except FileNotFoundError as e:
        print(f"[underlying] SKIP: {e}")

    snapshots = list_option_snapshots(args.symbol)
    target_date = args.options_date or (snapshots[-1] if snapshots else None)
    if target_date is None:
        print(f"[options] SKIP: no snapshots for {args.symbol}")
        return 0

    chain, meta = load_option_chain(args.symbol, target_date)
    spot = float(meta["spot"].iloc[0]) if not meta.empty else float("nan")
    print(check_option_chain(chain, symbol=args.symbol, spot=spot).render())

    if not args.no_continuity and len(snapshots) >= 2:
        loaded = [
            (date_str, *load_option_chain(args.symbol, date_str))
            for date_str in snapshots
        ]
        print(check_snapshot_continuity(args.symbol, loaded).render())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
