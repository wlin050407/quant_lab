"""Verify ThetaData credentials and Value-tier SPX / 0DTE access.

Examples:

    python scripts/verify_thetadata.py
    python scripts/verify_thetadata.py --date 2025-05-22
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from quant_lab.data.thetadata_client import get_thetadata_client
from quant_lab.data.thetadata_intraday import (
    fetch_0dte_chain_at_time,
    fetch_spx_at_time,
    fetch_spx_price_1m,
    list_index_symbols,
    resolve_option_root,
)

log = logging.getLogger(__name__)

_SUBSCRIPTION_LABEL = {0: "FREE", 1: "Value", 2: "Standard", 3: "Pro"}


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _subscription_label(tier: int | None) -> str:
    if tier is None:
        return "unknown"
    return _SUBSCRIPTION_LABEL.get(tier, f"tier={tier}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        type=_parse_date,
        default=None,
        help="session date (default: last weekday)",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    session_date = args.date
    if session_date is None:
        session_date = date.today()
        while session_date.weekday() >= 5:
            session_date -= timedelta(days=1)

    print("=== ThetaData verify ===")
    print(f"session_date={session_date}")
    print()

    try:
        client = get_thetadata_client(dataframe_type="pandas")
    except Exception as exc:
        print(f"FAIL auth: {exc}", file=sys.stderr)
        print()
        print("Setup: create C:\\Users\\ROG\\.thetadata\\creds.txt (email line 1, password line 2)")
        print("Add to e:\\quant_lab\\.env :")
        print("  THETADATA_CREDENTIALS_FILE=C:\\Users\\ROG\\.thetadata\\creds.txt")
        return 1

    print("OK  authenticated")
    print(
        f"    subscriptions: options={_subscription_label(client.options_subscription)}  "
        f"indices={_subscription_label(client.index_subscription)}  "
        f"stock={_subscription_label(client.stock_subscription)}"
    )
    print()

    indices_ok = False
    options_ok = False

    try:
        idx_syms = list_index_symbols(client)
        has_spx = "SPX" in set(idx_syms.get("symbol", idx_syms.iloc[:, 0]).astype(str))
        print(f"OK  index symbols ({len(idx_syms)} rows), SPX listed={has_spx}")
    except Exception as exc:
        print(f"WARN index_list_symbols: {exc}")

    opt_root = resolve_option_root(client)
    print(f"OK  option root → {opt_root!r}")

    if client.index_subscription < 1:
        print()
        print(
            "SKIP indices — account has FREE tier (need Indices Value for SPX 1m / at_time). "
            "Upgrade: https://www.thetadata.net/subscribe"
        )
    else:
        try:
            spot = fetch_spx_at_time(client, session_date=session_date, time_of_day="13:00:00")
            price = float(spot["price"].iloc[-1]) if not spot.empty else float("nan")
            print(f"OK  SPX @ 13:00 ET → {price:.2f}")
            indices_ok = True
        except Exception as exc:
            print(f"FAIL SPX at_time: {exc}")

        try:
            bars = fetch_spx_price_1m(
                client,
                session_date=session_date,
                start_time="12:00:00",
                end_time="14:00:00",
            )
            print(f"OK  SPX 1m price (12:00-14:00) → {len(bars)} rows")
            indices_ok = indices_ok and len(bars) > 0
        except Exception as exc:
            print(f"FAIL SPX 1m history: {exc}")

    try:
        chain = fetch_0dte_chain_at_time(
            client,
            session_date=session_date,
            time_of_day="13:00:00",
            option_root=opt_root,
            strike_range=30,
        )
        print(f"OK  0DTE {opt_root} quotes @ 13:00 → {len(chain)} contracts")
        if not chain.empty and "bid" in chain.columns:
            mid = (chain["bid"].astype(float) + chain["ask"].astype(float)) / 2.0
            print(f"    sample mid range: {mid.min():.2f} – {mid.max():.2f}")
        options_ok = len(chain) > 0
    except Exception as exc:
        print(f"FAIL 0DTE quotes: {exc}")

    print()
    if options_ok and indices_ok:
        print("All checks passed — ready for full backfill (spot + options).")
        return 0
    if options_ok:
        print(
            "Partial pass — 0DTE options OK. SPX spot backfill blocked until Indices Value "
            "is active on your account."
        )
        return 0
    if indices_ok:
        print("Partial pass — indices OK but 0DTE options failed.")
        return 4
    print("FAIL — neither indices nor 0DTE options verified.")
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
