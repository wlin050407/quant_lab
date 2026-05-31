"""Calibrate SPY → SPX GEX mapping from paired on-disk snapshots.

Examples:

    python scripts/calibrate_spx_spy.py
    python scripts/calibrate_spx_spy.py --date 2026-05-20
    python scripts/calibrate_spx_spy.py --write-config
    python scripts/calibrate_spx_spy.py --proxy --date 2026-05-20
"""

from __future__ import annotations

import argparse
import logging
import sys

from quant_lab.data.storage import load_option_chain
from quant_lab.factors.calibration import compute_gex_snapshot
from quant_lab.factors.spx_spy_calibration import (
    DEFAULT_SPX_SYMBOL,
    DEFAULT_SPY_SYMBOL,
    aggregate_paired_calibration,
    calibrate_paired_day,
    list_paired_snapshot_dates,
    load_calibration_params,
    save_calibration_params,
    spx_chain_quality,
    spy_to_spx_proxy,
)

log = logging.getLogger(__name__)


def _spot_from_meta(meta) -> float:
    if meta.empty:
        return float("nan")
    return float(meta["spot"].iloc[0])


def _run_paired_date(
    asof: str,
    *,
    spy_symbol: str,
    spx_symbol: str,
    params,
):
    spy_chain, spy_meta = load_option_chain(spy_symbol, asof)
    spy_spot = _spot_from_meta(spy_meta)
    spy_snap = compute_gex_snapshot(spy_chain, spot=spy_spot, asof_date=asof)

    try:
        spx_chain, spx_meta = load_option_chain(spx_symbol, asof)
    except FileNotFoundError:
        print(f"[SKIP] {asof}: no {spx_symbol} snapshot")
        proxy = spy_to_spx_proxy(spy_snap, params)
        print(
            f"SPY-only proxy SPX GEX={proxy.net_gex_bn_per_1pct:+.2f} Bn/1%  "
            f"flip≈{proxy.flip_level:.2f}"
        )
        print()
        return None

    spx_spot = _spot_from_meta(spx_meta)
    spx_snap = compute_gex_snapshot(spx_chain, spot=spx_spot, asof_date=asof)
    quality = spx_chain_quality(
        spx_chain["open_interest"],
        min_oi_rows=params.min_spx_oi_rows,
    )
    paired = calibrate_paired_day(
        spy_snap, spx_snap, spx_usable=quality.usable
    )

    print(f"--- {asof} ---")
    print(
        f"SPY spot={spy_snap.spot:.2f}  GEX={spy_snap.net_gex_bn_per_1pct:+.2f} Bn/1%  "
        f"regime={spy_snap.regime}"
    )
    print(
        f"SPX spot={spx_snap.spot:.2f}  GEX={spx_snap.net_gex_bn_per_1pct:+.2f} Bn/1%  "
        f"regime={spx_snap.regime}  OI rows={quality.oi_rows}/{quality.rows}  "
        f"usable={'yes' if quality.usable else 'NO'}"
    )
    print(
        f"strike_scale={paired.strike_scale:.4f}  "
        f"gex_k={'empirical' if quality.usable else 'theoretical'}={paired.gex_scale_k:.2f}  "
        f"regime_match={'OK' if paired.regime_match else 'MISMATCH'}"
    )
    if paired.flip_scale is not None:
        print(f"flip_scale={paired.flip_scale:.4f}")
    proxy = spy_to_spx_proxy(spy_snap, params, spx_spot=spx_snap.spot)
    print(
        f"proxy SPX GEX={proxy.net_gex_bn_per_1pct:+.2f} Bn/1%  "
        f"flip={proxy.flip_level:.2f}  method={proxy.method}"
    )
    print()
    return paired


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spy-symbol", default=DEFAULT_SPY_SYMBOL)
    parser.add_argument("--spx-symbol", default=DEFAULT_SPX_SYMBOL)
    parser.add_argument("--date", default=None, help="one YYYY-MM-DD; default all paired dates")
    parser.add_argument(
        "--write-config",
        action="store_true",
        help="write aggregate params to config/spx_spy_calibration.yaml",
    )
    parser.add_argument(
        "--proxy",
        action="store_true",
        help="SPY-only proxy for --date (no SPX required)",
    )
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    params = load_calibration_params()
    dates = [args.date] if args.date else list_paired_snapshot_dates(
        args.spy_symbol, args.spx_symbol
    )

    if args.proxy:
        if not args.date:
            print("--proxy requires --date", file=sys.stderr)
            return 1
        spy_chain, spy_meta = load_option_chain(args.spy_symbol, args.date)
        spy_snap = compute_gex_snapshot(
            spy_chain, spot=_spot_from_meta(spy_meta), asof_date=args.date
        )
        proxy = spy_to_spx_proxy(spy_snap, params)
        print(f"=== SPX proxy from SPY {args.date} ===")
        print(f"spy_spot={proxy.spy_spot:.2f}  spx_spot≈{proxy.spx_spot:.2f}")
        print(f"net GEX≈{proxy.net_gex_bn_per_1pct:+.2f} Bn/1%  k={proxy.gex_scale_k:.2f}")
        print(f"regime={proxy.regime}  flip≈{proxy.flip_level:.2f}  method={proxy.method}")
        return 0

    if not dates:
        print("no paired SPY/^SPX snapshot dates on disk", file=sys.stderr)
        print(
            f"fetch both: python scripts/fetch_option_chain.py --symbol {args.spy_symbol}",
            file=sys.stderr,
        )
        print(
            f"            python scripts/fetch_option_chain.py --symbol {args.spx_symbol}",
            file=sys.stderr,
        )
        return 1

    print(f"SPY→SPX calibration — {len(dates)} paired day(s)")
    print(f"loaded config method={params.method}  gex_scale_k={params.gex_scale_k}")
    print()

    pairs = []
    for asof in dates:
        paired = _run_paired_date(
            asof,
            spy_symbol=args.spy_symbol,
            spx_symbol=args.spx_symbol,
            params=params,
        )
        if paired is not None and hasattr(paired, "date"):
            pairs.append(paired)

    if args.write_config and pairs:
        agg = aggregate_paired_calibration(pairs)
        notes = (
            "Auto-generated by scripts/calibrate_spx_spy.py. "
            f"{sum(1 for p in pairs if p.spx_usable)}/{len(pairs)} days had usable SPX OI."
        )
        out = save_calibration_params(agg, notes=notes)
        print(f"wrote {out}")
        print(
            f"method={agg.method}  gex_scale_k={agg.gex_scale_k}  "
            f"strike_scale={agg.strike_scale:.4f}"
        )

    regime_ok = sum(1 for p in pairs if p.regime_match)
    print(f"summary: {len(pairs)} paired, regime_match {regime_ok}/{len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
