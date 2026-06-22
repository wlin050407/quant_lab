#!/usr/bin/env python3
"""ML-P8B.3.5 feature stability diagnostics CLI (no model fitting)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.harness.feature_diagnostics import (  # noqa: E402
    HARNESS_STAGE_P8B3_5,
    load_p8b35_config,
    run_p8b35_diagnostics,
)

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="ML-P8B.3.5 feature stability diagnostics")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ml/p8b3_feature_stability_diagnostics.yaml"),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preflight only; no diagnostic artifacts written",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config_path = args.config if args.config.is_absolute() else _PROJECT_ROOT / args.config
    config = load_p8b35_config(config_path)
    if args.output_dir is not None:
        config.output_reports = args.output_dir

    dry_run = bool(args.dry_run)
    log.info("%s mode=%s", HARNESS_STAGE_P8B3_5, "dry-run" if dry_run else "execute")

    result = run_p8b35_diagnostics(
        config,
        project_root=_PROJECT_ROOT,
        dry_run=dry_run,
    )
    print(json.dumps(result.to_dict(), indent=2))

    if not result.p8b3_5_pass:
        log.error("P8B.3.5 gate FAILED")
        return 1
    log.info("P8B.3.5 gate PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
