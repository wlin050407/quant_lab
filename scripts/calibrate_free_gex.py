"""Free GEX calibration — public YAML refs + optional FlashAlpha live cross-check.

Examples:

    python scripts/calibrate_free_gex.py
    python scripts/calibrate_free_gex.py --date 2024-08-05
    python scripts/calibrate_free_gex.py --live-flashalpha --symbol SPY

Live FlashAlpha cross-check reads ``FLASHALPHA_API_KEY`` from project ``.env``.
"""

from __future__ import annotations

import argparse
import logging
import sys

from quant_lab.config import settings
from quant_lab.data.flashalpha_gex import FlashAlphaError, fetch_gex
from quant_lab.data.storage import load_option_chain
from quant_lab.factors.calibration import (
    check_against_external_gex,
    check_against_reference,
    compute_gex_snapshot,
    load_all_references,
)

log = logging.getLogger(__name__)


def _run_yaml_refs(
    *,
    symbol: str,
    refs: list[dict],
    tolerance_pct: float,
) -> tuple[int, int]:
    n_pass = 0
    n_fail = 0
    for ref in refs:
        asof = str(ref["date"])
        provider = str(ref.get("provider", "yaml"))
        try:
            chain, meta = load_option_chain(symbol, asof)
        except FileNotFoundError:
            print(f"[SKIP] {asof} ({provider}): no snapshot on disk")
            continue

        spot = float(meta["spot"].iloc[0]) if not meta.empty else float("nan")
        snap = compute_gex_snapshot(chain, spot=spot, asof_date=asof)
        result = check_against_reference(snap, ref, tolerance_pct=tolerance_pct)

        status = "PASS" if result.passed else "FAIL"
        if result.passed:
            n_pass += 1
        else:
            n_fail += 1

        print(f"--- {asof} [{provider}] [{status}] ---")
        print(f"source: {ref.get('source', 'n/a')}")
        print(
            f"spot={snap.spot:.2f}  net_gex={snap.net_gex_bn_per_1pct:+.2f} Bn/1%  "
            f"flip={snap.flip_level:.2f}  regime={snap.regime}"
        )
        for msg in result.messages:
            print(f"  {msg}")
        print()

    return n_pass, n_fail


def _run_live_flashalpha(
    *,
    symbol: str,
    asof: str,
    tolerance_pct: float,
) -> tuple[int, int]:
    try:
        ext = fetch_gex(symbol, snapshot_date=asof)
    except FlashAlphaError as exc:
        print(f"[SKIP] FlashAlpha live: {exc}")
        return 0, 0

    try:
        chain, meta = load_option_chain(symbol, asof)
    except FileNotFoundError:
        print(f"[SKIP] FlashAlpha live: no local snapshot for {asof}")
        return 0, 0

    spot = float(meta["spot"].iloc[0]) if not meta.empty else float("nan")
    snap = compute_gex_snapshot(chain, spot=spot, asof_date=asof)
    result = check_against_external_gex(
        snap,
        external_regime=ext.regime,
        external_net_gex_bn_per_1pct=ext.net_gex_bn_per_1pct,
        external_flip=ext.gamma_flip,
        external_spot=ext.spot,
        provider="flashalpha",
        tolerance_pct=tolerance_pct,
    )

    status = "PASS" if result.passed else "FAIL"
    print(f"--- {asof} [flashalpha live] [{status}] ---")
    print(f"FA as_of={ext.as_of}  expiration={ext.expiration}  spot={ext.spot:.2f}  "
          f"net_gex={ext.net_gex_bn_per_1pct:+.2f} Bn/1%")
    print(f"flip={ext.gamma_flip:.2f}  regime={ext.regime}")
    for msg in result.messages:
        print(f"  {msg}")
    print()
    return (1, 0) if result.passed else (0, 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--date", default=None, help="run one YAML date only")
    parser.add_argument(
        "--tolerance-pct",
        type=float,
        default=0.30,
        help="allowed relative error for magnitude fields (default 30%%)",
    )
    parser.add_argument(
        "--live-flashalpha",
        action="store_true",
        help="also compare latest on-disk snapshot vs FlashAlpha live API",
    )
    parser.add_argument(
        "--flashalpha-date",
        default=None,
        help="local snapshot date for live FlashAlpha compare (default: latest chain)",
    )
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    refs = load_all_references()
    if args.date is not None:
        refs = [r for r in refs if str(r.get("date")) == args.date]
        if not refs and not args.live_flashalpha:
            print(f"no reference entry for date {args.date}", file=sys.stderr)
            return 1

    print(f"Free GEX calibration — {args.symbol} (tolerance ±{args.tolerance_pct:.0%})")
    print()

    n_pass, n_fail = _run_yaml_refs(
        symbol=args.symbol,
        refs=refs,
        tolerance_pct=args.tolerance_pct,
    )

    if args.live_flashalpha:
        asof = args.flashalpha_date
        if asof is None:
            chain_root = settings.paths.raw / "options" / args.symbol
            dates = sorted(p.name for p in chain_root.iterdir() if p.is_dir())
            if not dates:
                print("[SKIP] FlashAlpha live: no local snapshots", file=sys.stderr)
            else:
                asof = dates[-1]
        if asof is not None:
            p, f = _run_live_flashalpha(
                symbol=args.symbol,
                asof=asof,
                tolerance_pct=args.tolerance_pct,
            )
            n_pass += p
            n_fail += f

    print(f"summary: {n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
