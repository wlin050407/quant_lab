"""Fetch underlying OHLCV bars and append to local Parquet store.

Examples:

    python scripts/fetch_underlying.py --symbol ^GSPC
    python scripts/fetch_underlying.py --symbol AAPL --period 2y --interval 1d
"""

from __future__ import annotations

import argparse
import logging
import sys

from quant_lab.config import settings
from quant_lab.data.storage import save_underlying
from quant_lab.data.yfinance_source import YFinanceSource
from quant_lab.quality.checks import check_underlying


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, help="e.g. ^GSPC, SPY, AAPL")
    parser.add_argument("--period", default=settings.underlying.period)
    parser.add_argument("--interval", default=settings.underlying.interval)
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
    df = src.get_underlying(args.symbol, period=args.period, interval=args.interval)

    report = check_underlying(df, symbol=args.symbol)
    print(report.render())
    if report.has_errors:
        print("ERROR: data quality checks failed — refusing to write.", file=sys.stderr)
        return 2

    path = save_underlying(df, symbol=args.symbol, interval=args.interval)
    print(f"OK: wrote {len(df)} rows to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
