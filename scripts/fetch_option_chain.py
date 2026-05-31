"""Fetch a full option-chain snapshot for one symbol and save to Parquet.

The snapshot is timestamped (UTC) and partitioned by date — each run produces
a new folder under `data/raw/options/{symbol}/{YYYY-MM-DD}/`.

Examples:

    python scripts/fetch_option_chain.py --symbol ^GSPC
    python scripts/fetch_option_chain.py --symbol SPY --max-expiries 8
"""

from __future__ import annotations

import argparse
import logging
import sys

from quant_lab.config import settings
from quant_lab.data.storage import save_option_chain
from quant_lab.data.yfinance_source import YFinanceSource
from quant_lab.quality.checks import check_option_chain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument(
        "--max-expiries",
        type=int,
        default=settings.option_chain.max_expiries,
        help="how many nearest expiries to pull",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    src = YFinanceSource(
        request_sleep_seconds=float(
            settings.data_source_config.get("request_sleep_seconds", 0.4)
        )
    )
    snap = src.get_option_chain(args.symbol, max_expiries=args.max_expiries)

    report = check_option_chain(snap.chain, symbol=args.symbol, spot=snap.spot)
    print(report.render())
    if report.has_errors:
        print("ERROR: data quality checks failed — refusing to write.", file=sys.stderr)
        return 2

    path = save_option_chain(snap)
    print(
        f"OK: wrote {len(snap.chain)} rows, "
        f"{snap.chain['expiry'].nunique()} expiries, "
        f"spot={snap.spot:.2f} → {path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
