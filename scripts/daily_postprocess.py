"""Incremental processed-data refresh after daily raw fetches.

Runs terminal history (append-only) for symbols with snapshots, then rebuilds
Trinity alignment. Safe to run daily — skips symbols with no new dates.

Example:

    python scripts/daily_postprocess.py
    python scripts/daily_postprocess.py --symbols SPY ^SPX QQQ
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from quant_lab.data.storage import list_option_snapshots

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYMBOLS = ("SPY", "^SPX", "QQQ")


def _run_script(script: str, *args: str) -> int:
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / script), *args]
    log.info("run: %s", " ".join(cmd))
    return subprocess.call(cmd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=list(DEFAULT_SYMBOLS),
        help="symbols to refresh terminal parquet for",
    )
    parser.add_argument("--skip-trinity", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    failed: list[str] = []
    for symbol in args.symbols:
        n = len(list_option_snapshots(symbol))
        if n == 0:
            log.warning("skip %s — no option snapshots on disk", symbol)
            continue
        code = _run_script("build_terminal_history.py", "--symbol", symbol)
        if code != 0:
            failed.append(f"terminal:{symbol}")

    if not args.skip_trinity:
        code = _run_script("build_trinity_history.py")
        if code != 0:
            failed.append("trinity")

    if failed:
        print(f"postprocess failed: {', '.join(failed)}", file=sys.stderr)
        return 1

    print("postprocess OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
