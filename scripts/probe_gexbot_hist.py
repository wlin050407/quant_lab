"""Probe GEXBot hist coverage and prefetch available sessions."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date

from quant_lab.config import load_dotenv_if_present
from quant_lab.data.gexbot_client import GexbotConfigError
from quant_lab.data.gexbot_hist_probe import probe_and_prefetch

log = logging.getLogger(__name__)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    load_dotenv_if_present()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY", help="SPY or SPX (maps to GEXBot ticker)")
    parser.add_argument("--start", type=_parse_date, default=date(2025, 1, 1))
    parser.add_argument("--end", type=_parse_date, default=date.today())
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="metadata probe only; do not download hist JSON",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    sym = f"^{args.symbol.upper()}" if args.symbol.upper() == "SPX" else args.symbol.upper()
    try:
        result = probe_and_prefetch(
            sym,
            start=args.start,
            end=args.end,
            prefetch=not args.probe_only,
        )
    except GexbotConfigError as exc:
        print(json.dumps({"status": "skipped", "reason": str(exc)}, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    cov = result.get("coverage", {})
    n = cov.get("n_available", 0)
    if n < 200:
        log.warning("GEXBot hist coverage n=%s < 200 — V1 full gate still blocked", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
