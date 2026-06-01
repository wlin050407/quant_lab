"""Rebuild SPXW 0DTE intraday chains (same path as Terminal live).

Uses ``build_0dte_chain_snapshot`` so every chain includes Standard-tier
session trade volume, open OI reference, and effective OI — identical to live.

Examples::

    python scripts/build_thetadata_intraday_chains.py --all --force
    python scripts/build_thetadata_intraday_chains.py --date 2023-07-11
    python scripts/build_thetadata_intraday_chains.py --start 2023-01-03 --end 2023-07-31 --force
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta

from quant_lab.data.thetadata_chain import (
    build_0dte_chain_snapshot,
    list_intraday_chain_dates,
    save_built_intraday_chain,
)
from quant_lab.data.thetadata_client import DEFAULT_OPTION_ROOT, refresh_thetadata_client
from quant_lab.data.thetadata_intraday import PIN_PLAY_TIMES_ET
from quant_lab.data.thetadata_storage import intraday_chain_path

log = logging.getLogger(__name__)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _iter_weekdays(start: date, end: date) -> list[date]:
    out: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def _is_session_error(exc: BaseException) -> bool:
    msg = str(exc)
    return "Invalid session ID" in msg or "UNAUTHENTICATED" in msg


def _is_missing_data(exc: BaseException) -> bool:
    msg = str(exc)
    return "No data found" in msg or "no 0DTE quotes" in msg or "FileNotFoundError" in msg


def _resolve_session_dates(args: argparse.Namespace) -> list[date]:
    if args.all:
        return [date.fromisoformat(iso) for iso in list_intraday_chain_dates(option_root=DEFAULT_OPTION_ROOT)]
    if args.date is not None:
        return [args.date]
    if args.start is not None and args.end is not None:
        return _iter_weekdays(args.start, args.end)
    raise SystemExit("provide --all, --date, or --start/--end")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="every date with an existing intraday chain dir")
    parser.add_argument("--date", type=_parse_date, default=None)
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--force", action="store_true", help="overwrite existing chain_*.parquet")
    parser.add_argument("--strike-range", type=int, default=80)
    parser.add_argument("--progress-every", type=int, default=25, help="log progress every N snapshots")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    session_dates = _resolve_session_dates(args)
    if not session_dates:
        print("no session dates to build", file=sys.stderr)
        return 1

    client = refresh_thetadata_client(dataframe_type="pandas")
    option_root = DEFAULT_OPTION_ROOT
    built = 0
    skipped = 0
    failed = 0
    missing = 0
    total = len(session_dates) * len(PIN_PLAY_TIMES_ET)
    t0 = time.monotonic()
    done = 0

    print(
        f"rebuild {len(session_dates)} sessions × {len(PIN_PLAY_TIMES_ET)} times "
        f"= {total} snapshots  force={args.force}",
        flush=True,
    )

    for session_date in session_dates:
        for tod in PIN_PLAY_TIMES_ET:
            done += 1
            label = tod[:5].replace(":", "")
            out_path = intraday_chain_path(session_date, label, symbol=option_root)
            if not args.force and out_path.is_file():
                skipped += 1
                continue

            def _build(c):
                return build_0dte_chain_snapshot(
                    c,
                    session_date=session_date,
                    time_of_day=tod,
                    option_root=option_root,
                    strike_range=args.strike_range,
                )

            try:
                snapshot = _build(client)
            except Exception as exc:
                if _is_session_error(exc):
                    log.warning("session expired — reconnecting (%s @ %s)", session_date, tod)
                    client = refresh_thetadata_client(dataframe_type="pandas")
                    try:
                        snapshot = _build(client)
                    except Exception as exc2:
                        if _is_missing_data(exc2):
                            missing += 1
                            log.debug("no data %s @ %s: %s", session_date, tod, exc2)
                        else:
                            failed += 1
                            log.error("build failed %s @ %s: %s", session_date, tod, exc2)
                        continue
                elif _is_missing_data(exc):
                    missing += 1
                    log.debug("no data %s @ %s: %s", session_date, tod, exc)
                    continue
                else:
                    failed += 1
                    log.error("build failed %s @ %s: %s", session_date, tod, exc)
                    continue

            save_built_intraday_chain(
                snapshot,
                session_date=session_date,
                time_of_day=tod,
                option_root=option_root,
            )
            built += 1

            if done % args.progress_every == 0 or done == total:
                elapsed = time.monotonic() - t0
                rate = built / elapsed if elapsed > 0 and built else 0.0
                eta_s = (total - done) / (done / elapsed) if done > 0 else 0.0
                print(
                    f"progress {done}/{total}  built={built} skipped={skipped} "
                    f"missing={missing} failed={failed}  "
                    f"elapsed={elapsed / 3600:.1f}h  eta={eta_s / 3600:.1f}h  "
                    f"build_rate={rate * 3600:.0f}/h",
                    flush=True,
                )

    elapsed = time.monotonic() - t0
    print(
        f"done: built={built} skipped={skipped} missing={missing} failed={failed} "
        f"elapsed={elapsed / 3600:.2f}h",
        flush=True,
    )
    return 0 if built > 0 or skipped > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
