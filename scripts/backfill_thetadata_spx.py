"""Backfill SPX 1m prices + 0DTE option quotes at Pin Play times (ThetaData).

Requires ``THETADATA_CREDENTIALS_FILE`` or email/password in ``.env``.

Indices **Value** tier only includes SPX intraday history from ~2023 onward; older
dates need Indices Standard. Options Value history for SPXW 0DTE starts ~2022.

Examples:

    python scripts/backfill_thetadata_spx.py --days 3
    python scripts/backfill_thetadata_spx.py --start 2022-01-01 --end 2025-05-20
    python scripts/backfill_thetadata_spx.py --start 2022-01-01 --index-start 2023-01-03
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from quant_lab.data.thetadata_chain import (
    _spot_from_local_1m,
    build_0dte_chain_snapshot,
    save_built_intraday_chain,
)
from quant_lab.data.thetadata_client import get_thetadata_client, refresh_thetadata_client
from quant_lab.data.thetadata_intraday import (
    PIN_PLAY_TIMES_ET,
    fetch_0dte_chain_at_time,
    fetch_spx_price_1m,
    resolve_option_root,
)
from quant_lab.data.thetadata_storage import (
    intraday_chain_path,
    option_intraday_path,
    save_parquet,
    spx_price_1m_path,
)

log = logging.getLogger(__name__)

# First weekday verified on Indices Value (older dates require Standard tier).
DEFAULT_INDEX_HISTORY_START = date(2023, 1, 3)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _iter_weekdays(start: date, end: date) -> list[date]:
    days: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def _is_session_error(exc: BaseException) -> bool:
    msg = str(exc)
    return "Invalid session ID" in msg or "UNAUTHENTICATED" in msg


def _is_index_standard_required(exc: BaseException) -> bool:
    return "STANDARD subscription" in str(exc)


def _with_session_retry(client, fn, *, label: str):
    """Call ``fn(client)``; reconnect once on invalid session."""
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
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--index-start", type=_parse_date, default=DEFAULT_INDEX_HISTORY_START)
    parser.add_argument("--days", type=int, default=5, help="if no start/end: last N weekdays")
    parser.add_argument("--strike-range", type=int, default=80)
    parser.add_argument("--force", action="store_true", help="overwrite existing parquet files")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    end = args.end or date.today()
    if args.start is not None:
        start = args.start
    else:
        start = end
        counted = 0
        while counted < args.days:
            if start.weekday() < 5:
                counted += 1
            if counted < args.days:
                start -= timedelta(days=1)
        while start.weekday() >= 5:
            start -= timedelta(days=1)

    session_dates = _iter_weekdays(start, end)
    if not session_dates:
        print("no weekdays in range", file=sys.stderr)
        return 1

    try:
        client = get_thetadata_client(dataframe_type="pandas")
    except Exception as exc:
        print(f"auth failed: {exc}", file=sys.stderr)
        return 1

    option_root = resolve_option_root(client)
    indices_tier = getattr(client, "index_subscription", 0)
    index_start = args.index_start if indices_tier >= 1 else None

    print(
        f"backfill {start} → {end}  option_root={option_root}  days={len(session_dates)}"
    )
    if index_start is not None:
        print(f"SPX 1m from {index_start} (Indices Value; earlier dates need Standard tier)")
    else:
        log.warning("Indices subscription is FREE — skipping SPX 1m backfill")

    ok_price = 0
    ok_chain = 0
    ok_built = 0
    skip_price = 0
    fail_price = 0
    fail_chain = 0
    fail_built = 0

    for i, session_date in enumerate(session_dates, start=1):
        if index_start is not None and session_date >= index_start:
            price_path = spx_price_1m_path(session_date)
            if not args.force and price_path.is_file():
                skip_price += 1
            else:
                try:
                    bars, client = _with_session_retry(
                        client,
                        lambda c: fetch_spx_price_1m(c, session_date=session_date),
                        label=f"SPX 1m {session_date}",
                    )
                    if bars.empty:
                        log.warning("empty SPX 1m %s", session_date)
                    else:
                        save_parquet(bars, price_path)
                        ok_price += 1
                except Exception as exc:
                    if _is_index_standard_required(exc):
                        log.debug("SPX 1m skipped %s (Standard tier required)", session_date)
                    else:
                        log.error("SPX 1m failed %s: %s", session_date, exc)
                        fail_price += 1

        for tod in PIN_PLAY_TIMES_ET:
            label = tod[:5].replace(":", "")
            quotes_path = option_intraday_path(session_date, label, symbol=option_root)
            if not quotes_path.is_file() or args.force:
                try:
                    chain, client = _with_session_retry(
                        client,
                        lambda c: fetch_0dte_chain_at_time(
                            c,
                            session_date=session_date,
                            time_of_day=tod,
                            option_root=option_root,
                            strike_range=args.strike_range,
                        ),
                        label=f"0DTE {session_date} @ {tod}",
                    )
                    if chain.empty:
                        log.warning("empty 0DTE chain %s @ %s", session_date, tod)
                        continue
                    save_parquet(chain, quotes_path)
                    ok_chain += 1
                except Exception as exc:
                    if "No data found" in str(exc):
                        log.debug("no 0DTE quotes %s @ %s", session_date, tod)
                    else:
                        log.error("0DTE quotes failed %s @ %s: %s", session_date, tod, exc)
                        fail_chain += 1
                    continue

            built_path = intraday_chain_path(session_date, label, symbol=option_root)
            if not args.force and built_path.is_file():
                continue
            if not quotes_path.is_file():
                continue
            has_local_spot = _spot_from_local_1m(session_date, tod) is not None
            if index_start is not None and session_date < index_start and not has_local_spot:
                log.debug("skip chain build %s @ %s (no SPX spot before %s)", session_date, tod, index_start)
                continue
            try:
                snapshot, client = _with_session_retry(
                    client,
                    lambda c: build_0dte_chain_snapshot(
                        c,
                        session_date=session_date,
                        time_of_day=tod,
                        option_root=option_root,
                        strike_range=args.strike_range,
                    ),
                    label=f"build chain {session_date} @ {tod}",
                )
                save_built_intraday_chain(
                    snapshot,
                    session_date=session_date,
                    time_of_day=tod,
                    option_root=option_root,
                )
                ok_built += 1
            except Exception as exc:
                if "No data found" in str(exc) or "no 0DTE quotes" in str(exc):
                    log.debug("skip build %s @ %s", session_date, tod)
                else:
                    log.error("build chain failed %s @ %s: %s", session_date, tod, exc)
                    fail_built += 1

        if i % 25 == 0 or i == len(session_dates):
            print(
                f"progress {i}/{len(session_dates)}  "
                f"price_ok={ok_price} chain_ok={ok_chain} built_ok={ok_built} "
                f"price_skip={skip_price} price_fail={fail_price} "
                f"chain_fail={fail_chain} built_fail={fail_built}",
                flush=True,
            )

    print(
        f"done: price_days={ok_price}  chain_snapshots={ok_chain}  built_chains={ok_built}  "
        f"price_skip={skip_price}  price_fail={fail_price}  "
        f"chain_fail={fail_chain}  built_fail={fail_built}"
    )
    return 0 if ok_price > 0 or ok_chain > 0 or ok_built > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
