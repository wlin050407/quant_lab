#!/usr/bin/env python3
"""Run P8C.2 controlled ingest in batches until all frozen dates are terminal."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST = _PROJECT_ROOT / "artifacts/reports/p8c_raw_lake_ingest/p8c2_run_manifest.json"
_CONFIG = _PROJECT_ROOT / "config/ml/p8c2_raw_lake_ingest.yaml"


def main() -> int:
    batch = 0
    while True:
        batch += 1
        print(f"=== P8C.2 batch {batch} start ===", flush=True)
        t0 = time.time()
        proc = subprocess.run(
            [
                sys.executable,
                str(_PROJECT_ROOT / "scripts/run_p8c_controlled_ingest.py"),
                "--config",
                str(_CONFIG),
                "--execute",
                "--resume",
                "--max-dates",
                "5",
            ],
            cwd=_PROJECT_ROOT,
        )
        elapsed = time.time() - t0
        print(
            f"=== batch {batch} exit={proc.returncode} elapsed={elapsed:.0f}s ===",
            flush=True,
        )
        if proc.returncode != 0:
            return proc.returncode
        if not _MANIFEST.is_file():
            print("manifest missing", flush=True)
            return 1
        data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        pending = data.get("pending_dates", [])
        success_n = len(data.get("successful_dates", []))
        skipped_n = len(data.get("skipped_complete_dates", []))
        print(
            f"success={success_n} skipped={skipped_n} pending={len(pending)}",
            flush=True,
        )
        if not pending:
            print("ALL FROZEN DATES TERMINAL", flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
