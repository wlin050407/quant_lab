"""Build Heatseeker-ready intraday chains from saved ThetaData quotes + live OI.

Examples:

    python scripts/build_thetadata_intraday_chains.py --date 2023-07-11
    python scripts/build_thetadata_intraday_chains.py --start 2023-01-03 --end 2023-07-31
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

import numpy as np

from quant_lab.data.thetadata_chain import (
    _spot_from_local_1m,
    assemble_chain_from_quotes_oi,
    build_0dte_chain_snapshot,
    fetch_0dte_open_interest_at_time,
    save_built_intraday_chain,
)
from quant_lab.data.thetadata_client import DEFAULT_OPTION_ROOT, refresh_thetadata_client
from quant_lab.data.thetadata_intraday import PIN_PLAY_TIMES_ET
from quant_lab.data.thetadata_storage import (
    intraday_chain_path,
    load_parquet,
    option_intraday_path,
)

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
    return "Invalid session ID" in str(exc) or "UNAUTHENTICATED" in str(exc)


def _with_session_retry(client, fn, *, label: str):
    try:
        return fn(client), client
    except Exception as exc:
        if not _is_session_error(exc):
            raise
        log.warning("session expired during %s — reconnecting", label)
        client = refresh_thetadata_client(dataframe_type="pandas")
        return fn(client), client


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=_parse_date, default=None)
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--strike-range", type=int, default=80)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    if args.date is not None:
        session_dates = [args.date]
    elif args.start is not None and args.end is not None:
        session_dates = _iter_weekdays(args.start, args.end)
    else:
        print("provide --date or --start/--end", file=sys.stderr)
        return 1

    client = refresh_thetadata_client(dataframe_type="pandas")
    option_root = DEFAULT_OPTION_ROOT
    built = 0
    skipped = 0

    for session_date in session_dates:
        for tod in PIN_PLAY_TIMES_ET:
            label = tod[:5].replace(":", "")
            out_path = intraday_chain_path(session_date, label, symbol=option_root)
            if not args.force and out_path.is_file():
                skipped += 1
                continue
            quotes_path = option_intraday_path(session_date, label, symbol=option_root)
            if not quotes_path.is_file():
                log.debug("skip missing quotes %s @ %s", session_date, tod)
                continue
            try:
                quotes = load_parquet(quotes_path)

                def _fetch_oi(c):
                    return fetch_0dte_open_interest_at_time(
                        c,
                        session_date=session_date,
                        time_of_day=tod,
                        option_root=option_root,
                        strike_range=args.strike_range,
                    )

                oi, client = _with_session_retry(client, _fetch_oi, label=f"OI {session_date} @ {tod}")
            except Exception as exc:
                if _is_session_error(exc):
                    client = refresh_thetadata_client(dataframe_type="pandas")
                    try:
                        snapshot = build_0dte_chain_snapshot(
                            client,
                            session_date=session_date,
                            time_of_day=tod,
                            option_root=option_root,
                            strike_range=args.strike_range,
                        )
                        save_built_intraday_chain(
                            snapshot, session_date=session_date, time_of_day=tod, option_root=option_root
                        )
                        built += 1
                        continue
                    except Exception as exc2:
                        log.error("build failed %s @ %s: %s", session_date, tod, exc2)
                        continue
                log.error("OI failed %s @ %s: %s", session_date, tod, exc)
                continue

            try:
                spot = _spot_from_local_1m(session_date, tod)
                if spot is None or not np.isfinite(spot):
                    from quant_lab.data.thetadata_intraday import fetch_spx_at_time

                    spot_df = fetch_spx_at_time(client, session_date=session_date, time_of_day=tod)
                    spot = float(spot_df["price"].iloc[-1])
            except Exception:
                try:
                    snapshot = build_0dte_chain_snapshot(
                        client,
                        session_date=session_date,
                        time_of_day=tod,
                        option_root=option_root,
                        strike_range=args.strike_range,
                    )
                    save_built_intraday_chain(
                        snapshot, session_date=session_date, time_of_day=tod, option_root=option_root
                    )
                    built += 1
                    continue
                except Exception as exc:
                    log.error("spot+build failed %s @ %s: %s", session_date, tod, exc)
                    continue

            snapshot = assemble_chain_from_quotes_oi(
                quotes,
                oi,
                spot=spot,
                session_date=session_date,
                time_of_day=tod,
            )
            save_built_intraday_chain(
                snapshot, session_date=session_date, time_of_day=tod, option_root=option_root
            )
            built += 1

    print(f"done: built={built} skipped={skipped}")
    return 0 if built > 0 or skipped > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
