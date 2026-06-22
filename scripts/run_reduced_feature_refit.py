#!/usr/bin/env python3
"""ML-P8B.3.7 train-only reduced-feature learned refit."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.harness.p8b3_7_refit import (  # noqa: E402
    HARNESS_STAGE_P8B3_7,
    load_p8b37_config,
    parse_feature_set_ids,
    run_p8b37_refit,
)
from quant_lab.ml.harness.p8b3_fit import parse_target_groups  # noqa: E402

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ML-P8B.3.7 reduced-feature train-only refit (dry-run default)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ml/p8b3_reduced_feature_refit.yaml"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output_reports from config",
    )
    parser.add_argument(
        "--feature-set",
        type=str,
        default="A",
        help="Feature set id(s): A, B, or A,B",
    )
    parser.add_argument(
        "--targets",
        type=str,
        default="p0,p1_050,p1_025,p2_optional",
        help="Comma-separated: p0,p1_050,p1_025,p2_optional",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate only; no .fit()")
    mode.add_argument("--execute", action="store_true", help="Run train-only refit (P8B.3.7)")
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

    try:
        feature_set_ids = parse_feature_set_ids(args.feature_set)
    except ValueError as exc:
        log.error("%s", exc)
        return 2

    config_path = args.config if args.config.is_absolute() else _PROJECT_ROOT / args.config
    config = load_p8b37_config(config_path)
    if args.output_dir is not None:
        config.base.output_reports = args.output_dir
    config.reduced_feature_manifest = (
        config.reduced_feature_manifest
        if config.reduced_feature_manifest.is_absolute()
        else _PROJECT_ROOT / config.reduced_feature_manifest
    )
    config.base.dataset_root = (
        config.base.dataset_root
        if config.base.dataset_root.is_absolute()
        else _PROJECT_ROOT / config.base.dataset_root
    )
    config.base.feature_root = (
        config.base.feature_root
        if config.base.feature_root.is_absolute()
        else _PROJECT_ROOT / config.base.feature_root
    )
    config.base.p8b2_reports = (
        config.base.p8b2_reports
        if config.base.p8b2_reports.is_absolute()
        else _PROJECT_ROOT / config.base.p8b2_reports
    )
    config.p8b3_2_reports = (
        config.p8b3_2_reports
        if config.p8b3_2_reports.is_absolute()
        else _PROJECT_ROOT / config.p8b3_2_reports
    )
    config.base.output_reports = (
        config.base.output_reports
        if config.base.output_reports.is_absolute()
        else _PROJECT_ROOT / config.base.output_reports
    )

    targets = parse_target_groups(args.targets)
    log.info(
        "%s mode=%s feature_sets=%s targets=%s",
        HARNESS_STAGE_P8B3_7,
        "execute" if execute else "dry-run",
        feature_set_ids,
        sorted(targets),
    )

    result = run_p8b37_refit(
        config,
        project_root=_PROJECT_ROOT,
        feature_set_ids=feature_set_ids,
        targets=targets,
        split_mode=args.split_mode,
        execute=execute,
    )
    print(json.dumps(result.to_dict(), indent=2))

    if not result.p8b3_7_pass:
        log.error("P8B.3.7 gate FAILED")
        return 1
    log.info("P8B.3.7 gate PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
