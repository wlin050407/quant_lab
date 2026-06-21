#!/usr/bin/env python3
"""ML-P8B.2 model-free baseline evaluation (no sklearn .fit(), no learned models)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.harness.p8b2_eval import (  # noqa: E402
    SplitMode,
    build_dry_run_plan,
    load_p8b2_config,
    render_p8b2_markdown_report,
    run_p8b2_evaluation,
)

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="ML-P8B.2 model-free baseline evaluation")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ml/p8b2_model_free_baselines.yaml"),
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no evaluation")
    parser.add_argument(
        "--splits",
        choices=("chronological", "configured"),
        default="chronological",
        help="Session split mode",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output_reports from config",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    config = load_p8b2_config(args.config)
    if args.output_dir is not None:
        config.output_reports = args.output_dir

    if config.model_fitting_allowed:
        log.error("model_fitting_allowed must be false for P8B.2")
        return 2

    if args.dry_run:
        plan = build_dry_run_plan(config)
        print(json.dumps(plan, indent=2))
        if not plan.get("dataset_exists") or not plan.get("feature_exists"):
            log.error("input artifacts missing")
            return 2
        log.info("dry-run PASS")
        return 0

    split_mode: SplitMode = args.splits
    result = run_p8b2_evaluation(config, split_mode=split_mode, dry_run=False)

    if result.report_path and result.report_path.is_file():
        report_payload = json.loads(result.report_path.read_text(encoding="utf-8"))
        md_body = render_p8b2_markdown_report(report_payload, config)
        md_path = config.output_reports / "p8b2_model_free_baseline_report.md"
        md_path.write_text(md_body, encoding="utf-8")
        docs_md = _PROJECT_ROOT / "docs" / "ml" / "p8b2_model_free_baseline_report.md"
        docs_md.write_text(md_body, encoding="utf-8")
        log.info("markdown report: %s (docs: %s)", md_path, docs_md)

    log.info(
        "P8B.2 complete: p8b2_pass=%s manifest=%s",
        result.p8b2_pass,
        result.run_manifest_path,
    )
    if not result.p8b2_pass:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
