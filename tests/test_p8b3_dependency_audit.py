"""Tests for ML-P8B.3.0 dependency / environment audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_lab.ml.harness.p8b3_dependency_audit import (
    BANNED_SCRIPT_TOKENS,
    DependencyStatus,
    compute_dependency_status,
    evaluate_p8b3_1_proceed_rule,
    run_p8b3_dependency_audit,
    scan_dependency_files,
    write_audit_json,
)


def test_dependency_file_scan_detects_scikit_learn(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("numpy>=1.26\nscikit-learn>=1.4.0\npandas>=2.2\n", encoding="utf-8")
    scans = scan_dependency_files(tmp_path)
    req_scan = next(s for s in scans if s.path == "requirements.txt")
    assert req_scan.exists is True
    assert req_scan.scikit_learn_declared is True
    assert req_scan.declared_version_spec == "scikit-learn>=1.4.0"
    assert req_scan.numpy_declared is True
    assert req_scan.pandas_declared is True


def test_dependency_file_scan_handles_missing_files(tmp_path: Path) -> None:
    scans = scan_dependency_files(tmp_path)
    missing = [s for s in scans if not s.exists]
    assert len(missing) > 0
    assert all(not s.scikit_learn_declared for s in missing)


def test_dependency_status_declared_and_importable() -> None:
    status = compute_dependency_status(scikit_learn_declared=True, sklearn_importable=True)
    assert status is DependencyStatus.DECLARED_AND_IMPORTABLE
    may, reason = evaluate_p8b3_1_proceed_rule(status)
    assert may is True
    assert "may proceed" in reason


def test_dependency_status_importable_but_not_declared() -> None:
    status = compute_dependency_status(scikit_learn_declared=False, sklearn_importable=True)
    assert status is DependencyStatus.IMPORTABLE_BUT_NOT_DECLARED
    may, reason = evaluate_p8b3_1_proceed_rule(status)
    assert may is False
    assert "reproducible/CI" in reason


def test_dependency_status_declared_but_not_importable() -> None:
    status = compute_dependency_status(scikit_learn_declared=True, sklearn_importable=False)
    assert status is DependencyStatus.DECLARED_BUT_NOT_IMPORTABLE
    may, reason = evaluate_p8b3_1_proceed_rule(status)
    assert may is False
    assert "fix environment" in reason


def test_dependency_status_not_declared_not_importable() -> None:
    status = compute_dependency_status(scikit_learn_declared=False, sklearn_importable=False)
    assert status is DependencyStatus.NOT_DECLARED_NOT_IMPORTABLE
    may, reason = evaluate_p8b3_1_proceed_rule(status)
    assert may is False
    assert "request dependency approval" in reason


def test_audit_json_serializable(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("numpy>=1.26\n", encoding="utf-8")
    result = run_p8b3_dependency_audit(tmp_path)
    out = tmp_path / "audit.json"
    write_audit_json(result, out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["phase"] == "ML-P8B.3.0"
    assert "dependency_status" in payload
    assert payload["model_fitting_performed"] is False


def test_run_audit_does_not_require_sklearn_installed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "requirements.txt").write_text("numpy>=1.26\npandas>=2.2\n", encoding="utf-8")

    def _probe_no_sklearn() -> object:
        from quant_lab.ml.harness.p8b3_dependency_audit import EnvironmentVersions

        return EnvironmentVersions(python_version="3.12.0", numpy_version="1.26.0", pandas_version="2.2.0")

    monkeypatch.setattr(
        "quant_lab.ml.harness.p8b3_dependency_audit.probe_environment",
        _probe_no_sklearn,
    )
    result = run_p8b3_dependency_audit(tmp_path)
    assert result.p8b3_0_pass is True
    assert result.dependency_status == DependencyStatus.NOT_DECLARED_NOT_IMPORTABLE.value


def test_no_fitting_related_banned_tokens_in_audit_script() -> None:
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "audit_p8b3_environment.py"
    text = script_path.read_text(encoding="utf-8")
    for token in BANNED_SCRIPT_TOKENS:
        assert token not in text, f"banned token {token!r} found in {script_path.name}"
