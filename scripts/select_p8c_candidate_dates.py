#!/usr/bin/env python3
"""ML-P8C.1 expansion candidate date selection (no ingest / build / fit)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.datasets.p8c_date_selection import (  # noqa: E402
    HARNESS_STAGE_P8C1,
    load_p8c_selection_config,
    run_p8c1_selection,
)

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ML-P8C.1 candidate date selection (dry-run default; execute writes manifest)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ml/p8c_stage1_candidate_selection.yaml"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output_reports.output_dir from config",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate config only")
    mode.add_argument("--execute", action="store_true", help="Run selection and write manifest")
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
    config = load_p8c_selection_config(config_path)
    if args.output_dir is not None:
        config.output_dir = args.output_dir

    log.info("%s mode=%s", HARNESS_STAGE_P8C1, "execute" if execute else "dry-run")

    result = run_p8c1_selection(config, project_root=_PROJECT_ROOT, execute=execute)
    print(json.dumps(result.to_dict(), indent=2))

    if not result.p8c1_pass:
        log.error("P8C.1 gate FAILED: %s", result.errors)
        return 1
    log.info("P8C.1 gate PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
