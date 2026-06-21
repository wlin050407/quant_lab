#!/usr/bin/env python3
"""ML-P8B.3.2 train-only simple learned baseline fitting."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.harness.p8b3_fit import (  # noqa: E402
    HARNESS_STAGE_P8B3_2,
    load_p8b31_config,
    parse_target_groups,
    run_p8b32_fitting,
)

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ML-P8B.3.2 train-only simple learned baselines (dry-run default)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ml/p8b3_simple_learned_baselines.yaml"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output_reports from config",
    )
    parser.add_argument(
        "--targets",
        type=str,
        default="p0,p1_050,p1_025,p2_optional",
        help="Comma-separated: p0,p1_050,p1_025,p2_optional",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate only; no .fit()")
    mode.add_argument("--execute", action="store_true", help="Run train-only fitting (P8B.3.2)")
    parser.add_argument(
        "--split-mode",
        choices=("configured", "chronological"),
        default="configured",
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
    if execute and args.dry_run:
        log.error("cannot use --dry-run and --execute together")
        return 2

    config_path = args.config if args.config.is_absolute() else _PROJECT_ROOT / args.config
    config = load_p8b31_config(config_path)
    if args.output_dir is not None:
        config.output_reports = args.output_dir

    targets = parse_target_groups(args.targets)
    log.info(
        "%s mode=%s targets=%s",
        HARNESS_STAGE_P8B3_2,
        "execute" if execute else "dry-run",
        sorted(targets),
    )

    result = run_p8b32_fitting(
        config,
        project_root=_PROJECT_ROOT,
        targets=targets,
        split_mode=args.split_mode,
        execute=execute,
    )
    print(json.dumps(result.to_dict(), indent=2))

    if not result.p8b3_2_pass:
        log.error("P8B.3.2 gate FAILED")
        return 1
    log.info("P8B.3.2 gate PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
