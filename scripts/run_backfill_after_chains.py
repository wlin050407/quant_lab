"""Wait for intraday chain build to finish, then run full ThetaData backfill.

Examples:

    python scripts/run_backfill_after_chains.py
    python scripts/run_backfill_after_chains.py --poll-seconds 30
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_BUILD_SCRIPT = _ROOT / "scripts" / "build_thetadata_intraday_chains.py"
_BACKFILL_SCRIPT = _ROOT / "scripts" / "backfill_thetadata_spx.py"
_LOG_DIR = _ROOT / "logs"


def _chain_build_running() -> bool:
    try:
        import psutil
    except ImportError:
        psutil = None

    needle = "build_thetadata_intraday_chains.py"
    if psutil is not None:
        for proc in psutil.process_iter(["cmdline"]):
            try:
                cmdline = proc.info.get("cmdline") or []
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if any(needle in str(part) for part in cmdline):
                if proc.pid == __import__("os").getpid():
                    continue
                return True
        return False

    if sys.platform != "win32":
        return False
    import subprocess as sp

    out = sp.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like '*{needle}*' }} | Measure-Object | Select-Object -ExpandProperty Count",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        count = int(out.stdout.strip() or "0")
    except ValueError:
        return False
    return count > 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    backfill_log = _LOG_DIR / "backfill_after_chains.log"

    if _chain_build_running():
        log.info("chain build in progress — waiting before backfill")
        while _chain_build_running():
            time.sleep(args.poll_seconds)
    else:
        log.info("no chain build detected — starting backfill now")

    log.info("starting backfill → %s", backfill_log)
    with backfill_log.open("a", encoding="utf-8") as fh:
        fh.write("\n=== backfill started after chain build ===\n")
        proc = subprocess.run(
            [
                sys.executable,
                str(_BACKFILL_SCRIPT),
                "--start",
                "2022-01-01",
                "--log-level",
                "INFO",
            ],
            cwd=_ROOT,
            stdout=fh,
            stderr=subprocess.STDOUT,
            check=False,
        )
    log.info("backfill finished exit_code=%s", proc.returncode)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
