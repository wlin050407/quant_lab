#!/usr/bin/env python3
"""ML-P8B.3.0 dependency / environment audit CLI (no model fitting)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.harness.p8b3_dependency_audit import (  # noqa: E402
    HARNESS_STAGE_P8B3_0,
    run_p8b3_dependency_audit,
    write_audit_json,
)

log = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path("artifacts/reports/p8b3_dependency_audit/p8b3_dependency_audit.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="ML-P8B.3.0 dependency / environment audit")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=_PROJECT_ROOT,
        help="Project root to scan",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON audit report path (gitignored)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print summary only, do not write JSON")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    result = run_p8b3_dependency_audit(args.project_root.resolve())
    summary = {
        "phase": HARNESS_STAGE_P8B3_0,
        "dependency_status": result.dependency_status,
        "scikit_learn_declared": result.scikit_learn_declared,
        "sklearn_importable": result.environment.sklearn_importable if result.environment else False,
        "sklearn_version": result.environment.sklearn_version if result.environment else None,
        "dependency_approval_required": result.dependency_approval_required,
        "p8b3_1_may_proceed": result.p8b3_1_may_proceed,
        "p8b3_0_pass": result.p8b3_0_pass,
        "model_fitting_performed": False,
        "sklearn_fit_called": False,
    }
    print(json.dumps(summary, indent=2))

    if args.dry_run:
        log.info("dry-run complete — no JSON written")
        return 0

    out_path = write_audit_json(result, args.output)
    log.info("audit JSON written: %s", out_path)
    log.info(
        "P8B.3.0 complete: pass=%s status=%s p8b3_1_may_proceed=%s",
        result.p8b3_0_pass,
        result.dependency_status,
        result.p8b3_1_may_proceed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
