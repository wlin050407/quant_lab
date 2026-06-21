#!/usr/bin/env python3
"""ML-P8B.3.1 simple learned baseline harness — dry-run plan only (no .fit())."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.harness.p8b3_plan import (  # noqa: E402
    FIT_EXECUTION_BLOCKED_MSG,
    build_p8b31_fit_plan,
    load_p8b31_config,
    reject_fit_execution,
    validate_sklearn_dependency_declared,
    write_fit_plan_json,
)

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ML-P8B.3.1 simple learned baseline harness (dry-run default)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ml/p8b3_simple_learned_baselines.yaml"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build fit plan only (default behavior when --execute not set)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Request model fitting (blocked until P8B.3.2)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output_reports from config",
    )
    parser.add_argument(
        "--check-dependencies",
        action="store_true",
        help="Run sklearn dependency gate only",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    ok, msg = reject_fit_execution(execute_requested=args.execute)
    if not ok:
        print(msg)
        return 2

    if args.check_dependencies:
        gate = validate_sklearn_dependency_declared(_PROJECT_ROOT)
        print(json.dumps(gate.to_dict(), indent=2))
        return 0 if gate.passed else 1

    config = load_p8b31_config(args.config)
    if args.output_dir is not None:
        config.output_reports = args.output_dir

    if config.model_fitting_allowed:
        log.error("model_fitting_allowed must be false for P8B.3.1")
        return 2

    plan = build_p8b31_fit_plan(config, project_root=_PROJECT_ROOT, load_data=not args.check_dependencies)
    summary = {
        "phase": plan.phase,
        "dependency_status": plan.dependency_gate.dependency_status if plan.dependency_gate else None,
        "p8b3_1_pass": plan.p8b3_1_pass,
        "fit_execution_status": plan.fit_execution_status,
        "model_fitting_allowed": plan.model_fitting_allowed,
        "allowed_model_specs": [s["name"] for s in plan.allowed_model_specs],
        "split_summary": plan.split_summary,
    }
    print(json.dumps(summary, indent=2))

    if args.dry_run or not args.execute:
        out = config.output_reports / "p8b3_1_fit_plan.json"
        write_fit_plan_json(plan, out)
        log.info("fit plan written: %s", out)
        log.info("P8B.3.1 dry-run complete: pass=%s", plan.p8b3_1_pass)
        return 0 if plan.p8b3_1_pass else 1

    print(FIT_EXECUTION_BLOCKED_MSG)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
