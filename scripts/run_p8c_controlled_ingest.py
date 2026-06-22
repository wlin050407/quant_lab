#!/usr/bin/env python3
"""ML-P8C.2 controlled raw lake ingest for frozen Stage-1 expansion dates."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.datasets.p8c_controlled_ingest import (  # noqa: E402
    HARNESS_STAGE_P8C2,
    load_p8c2_ingest_config,
    run_p8c2_controlled_ingest,
    write_p8c2_artifacts,
)

log = logging.getLogger(__name__)


def _parse_dates(raw: str | None) -> list[date] | None:
    if raw is None:
        return None
    return [date.fromisoformat(part.strip()) for part in raw.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ML-P8C.2 controlled raw lake ingest (dry-run default; "
            "--execute performs ThetaData ingest for frozen dates only)"
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ml/p8c2_raw_lake_ingest.yaml"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output_reports from config",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preflight + ingest plan only")
    mode.add_argument("--execute", action="store_true", help="Perform actual raw lake ingest")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip dates with complete partitions (config.resume must be enabled)",
    )
    parser.add_argument(
        "--dates",
        type=str,
        default=None,
        help="Comma-separated YYYY-MM-DD subset of frozen_dates",
    )
    parser.add_argument(
        "--max-dates",
        type=int,
        default=None,
        help="Limit batch size (first N frozen dates in order)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    execute = bool(args.execute)
    if not execute and not args.dry_run:
        log.info("defaulting to dry-run (no --execute)")

    config_path = args.config if args.config.is_absolute() else _PROJECT_ROOT / args.config
    config = load_p8c2_ingest_config(config_path)
    output_dir = args.output_dir or config.output_reports
    if not output_dir.is_absolute():
        output_dir = _PROJECT_ROOT / output_dir

    log.info(
        "%s mode=%s resume=%s max_dates=%s",
        HARNESS_STAGE_P8C2,
        "execute" if execute else "dry-run",
        args.resume,
        args.max_dates,
    )

    result = run_p8c2_controlled_ingest(
        config,
        project_root=_PROJECT_ROOT,
        execute=execute,
        resume=args.resume,
        dates_filter=_parse_dates(args.dates),
        max_dates=args.max_dates,
    )
    paths = write_p8c2_artifacts(result, output_dir)
    print(json.dumps(result.to_dict(), indent=2))
    log.info("artifacts: %s", {k: str(v) for k, v in paths.items()})

    if result.gate_status == "FAIL":
        log.error("P8C.2 gate FAILED: %s", result.errors)
        return 1
    log.info("P8C.2 gate %s", result.gate_status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
