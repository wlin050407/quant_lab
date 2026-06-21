"""ML-P8B.3.0 dependency / environment audit (no model fitting)."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

HARNESS_STAGE_P8B3_0 = "ML-P8B.3.0"

DEPENDENCY_SCAN_FILES: tuple[str, ...] = (
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "environment.yml",
    "Pipfile",
    "poetry.lock",
    "uv.lock",
)

CI_DOCKER_SCAN_FILES: tuple[str, ...] = (
    "Dockerfile",
    ".github/workflows/ci.yml",
    ".github/workflows/test.yml",
    ".github/workflows/python.yml",
)

SCIKIT_LEARN_PACKAGE_NAMES: frozenset[str] = frozenset({"scikit-learn", "sklearn"})

BANNED_SCRIPT_TOKENS: frozenset[str] = frozenset(
    {
        ".fit(",
        "LinearRegression(",
        "Ridge(",
        "LogisticRegression(",
        "train_test_split(",
        "xgboost",
        "lightgbm",
        "torch",
    }
)


class DependencyStatus(StrEnum):
    DECLARED_AND_IMPORTABLE = "declared_and_importable"
    DECLARED_BUT_NOT_IMPORTABLE = "declared_but_not_importable"
    IMPORTABLE_BUT_NOT_DECLARED = "importable_but_not_declared"
    NOT_DECLARED_NOT_IMPORTABLE = "not_declared_not_importable"


@dataclass
class DependencyFileScan:
    path: str
    exists: bool
    scikit_learn_declared: bool = False
    declared_version_spec: str | None = None
    numpy_declared: bool = False
    pandas_declared: bool = False
    scipy_declared: bool = False
    lockfile_present: bool = False


@dataclass
class EnvironmentVersions:
    python_version: str
    numpy_version: str | None = None
    pandas_version: str | None = None
    scipy_version: str | None = None
    sklearn_importable: bool = False
    sklearn_version: str | None = None


@dataclass
class P8B3DependencyAuditResult:
    phase: str = HARNESS_STAGE_P8B3_0
    created_at: str = ""
    project_root: str = ""
    dependency_files_scanned: list[DependencyFileScan] = field(default_factory=list)
    dependency_file_found: bool = False
    scikit_learn_declared: bool = False
    declared_version_spec: str | None = None
    dependency_source_files: list[str] = field(default_factory=list)
    lockfile_present: bool = False
    ci_environment_mentions_sklearn: bool = False
    ci_docker_scan_hits: list[str] = field(default_factory=list)
    environment: EnvironmentVersions | None = None
    dependency_status: str = DependencyStatus.NOT_DECLARED_NOT_IMPORTABLE
    dependency_approval_required: bool = True
    p8b3_1_may_proceed: bool = False
    p8b3_1_proceed_reason: str = ""
    p8b3_0_pass: bool = False
    model_fitting_performed: bool = False
    sklearn_fit_called: bool = False
    dependency_files_modified: bool = False
    artifacts_not_committed: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.environment is not None:
            data["environment"] = asdict(self.environment)
        return data


def _parse_version_spec(line: str, package: str) -> str | None:
    pattern = re.compile(
        rf"^{re.escape(package)}\s*(==|>=|<=|~=|!=|>|<)\s*([^\s#;]+)",
        re.IGNORECASE,
    )
    match = pattern.match(line.strip())
    if match:
        return f"{package}{match.group(1)}{match.group(2)}"
    bare = re.match(rf"^{re.escape(package)}\s*$", line.strip(), re.IGNORECASE)
    if bare:
        return package
    return None


def _scan_file_content(path: Path) -> DependencyFileScan:
    rel = path.as_posix()
    scan = DependencyFileScan(path=rel, exists=True, lockfile_present=path.name.endswith(".lock"))
    text = path.read_text(encoding="utf-8", errors="replace")
    lower = text.lower()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        for pkg in ("scikit-learn", "sklearn"):
            spec = _parse_version_spec(stripped, pkg)
            if spec or re.search(rf"\b{re.escape(pkg)}\b", stripped, re.IGNORECASE):
                scan.scikit_learn_declared = True
                if spec and not scan.declared_version_spec:
                    scan.declared_version_spec = spec
        if re.search(r"\bnumpy\b", stripped, re.IGNORECASE):
            scan.numpy_declared = True
        if re.search(r"\bpandas\b", stripped, re.IGNORECASE):
            scan.pandas_declared = True
        if re.search(r"\bscipy\b", stripped, re.IGNORECASE):
            scan.scipy_declared = True
    if "scikit-learn" in lower or re.search(r"\bsklearn\b", lower):
        scan.scikit_learn_declared = True
    return scan


def scan_dependency_files(project_root: Path) -> list[DependencyFileScan]:
    """Scan known dependency declaration files under project root."""
    results: list[DependencyFileScan] = []
    for name in DEPENDENCY_SCAN_FILES:
        path = project_root / name
        if path.is_file():
            scan = _scan_file_content(path)
            scan.path = name
            results.append(scan)
        else:
            results.append(DependencyFileScan(path=name, exists=False))
    return results


def scan_ci_docker_mentions(project_root: Path) -> tuple[bool, list[str]]:
    """Return whether CI/Docker files mention sklearn/scikit-learn."""
    hits: list[str] = []
    for name in CI_DOCKER_SCAN_FILES:
        path = project_root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        if "scikit-learn" in text or re.search(r"\bsklearn\b", text):
            hits.append(path.as_posix())
    return bool(hits), hits


def _safe_version(module_name: str) -> str | None:
    try:
        import importlib.metadata as metadata

        return metadata.version(module_name)
    except Exception:
        return None


def _importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def probe_environment() -> EnvironmentVersions:
    """Record local Python and optional scientific stack versions."""
    env = EnvironmentVersions(python_version=sys.version.split()[0])
    if _importable("numpy"):
        env.numpy_version = _safe_version("numpy")
    if _importable("pandas"):
        env.pandas_version = _safe_version("pandas")
    if _importable("scipy"):
        env.scipy_version = _safe_version("scipy")
    if _importable("sklearn"):
        env.sklearn_importable = True
        env.sklearn_version = _safe_version("scikit-learn")
    return env


def compute_dependency_status(
    *,
    scikit_learn_declared: bool,
    sklearn_importable: bool,
) -> DependencyStatus:
    if scikit_learn_declared and sklearn_importable:
        return DependencyStatus.DECLARED_AND_IMPORTABLE
    if scikit_learn_declared and not sklearn_importable:
        return DependencyStatus.DECLARED_BUT_NOT_IMPORTABLE
    if not scikit_learn_declared and sklearn_importable:
        return DependencyStatus.IMPORTABLE_BUT_NOT_DECLARED
    return DependencyStatus.NOT_DECLARED_NOT_IMPORTABLE


def evaluate_p8b3_1_proceed_rule(status: DependencyStatus) -> tuple[bool, str]:
    if status is DependencyStatus.DECLARED_AND_IMPORTABLE:
        return True, "P8B.3.1 may proceed to limited simple learned baseline implementation."
    if status is DependencyStatus.IMPORTABLE_BUT_NOT_DECLARED:
        return (
            False,
            "P8B.3.1 cannot rely on sklearn in reproducible/CI environments until owner "
            "explicitly approves one of: (A) add scikit-learn to dependency declaration; "
            "(B) treat sklearn as externally provided runtime dependency and document CI "
            "limitation; (C) implement dependency-gated optional code that skips learned "
            "fitting when sklearn is unavailable.",
        )
    if status is DependencyStatus.DECLARED_BUT_NOT_IMPORTABLE:
        return False, "Stop and fix environment before implementation (declared but not importable)."
    return False, "Stop and request dependency approval (not declared, not importable)."


def run_p8b3_dependency_audit(project_root: Path) -> P8B3DependencyAuditResult:
    """Run full P8B.3.0 dependency audit without model fitting."""
    scans = scan_dependency_files(project_root)
    ci_mentions, ci_hits = scan_ci_docker_mentions(project_root)
    env = probe_environment()

    existing = [s for s in scans if s.exists]
    declared = any(s.scikit_learn_declared for s in existing)
    version_specs = [s.declared_version_spec for s in existing if s.declared_version_spec]
    source_files = [s.path for s in existing if s.scikit_learn_declared]
    lockfiles = [s.path for s in existing if s.lockfile_present]

    status = compute_dependency_status(
        scikit_learn_declared=declared,
        sklearn_importable=env.sklearn_importable,
    )
    may_proceed, proceed_reason = evaluate_p8b3_1_proceed_rule(status)
    approval_required = status is not DependencyStatus.DECLARED_AND_IMPORTABLE

    notes: list[str] = []
    if status is DependencyStatus.IMPORTABLE_BUT_NOT_DECLARED:
        notes.append(
            "P8B.3.1 cannot rely on sklearn in reproducible/CI environments until owner "
            "approves dependency declaration or confirms sklearn is available through the "
            "project environment."
        )
    if project_root.joinpath("pyproject.toml").is_file() and not declared:
        notes.append(
            "pyproject.toml uses dynamic dependencies from requirements.txt; scikit-learn "
            "is not declared in requirements.txt."
        )

    result = P8B3DependencyAuditResult(
        created_at=datetime.now(tz=UTC).isoformat(),
        project_root=str(project_root.resolve()),
        dependency_files_scanned=scans,
        dependency_file_found=bool(existing),
        scikit_learn_declared=declared,
        declared_version_spec=version_specs[0] if version_specs else None,
        dependency_source_files=source_files,
        lockfile_present=bool(lockfiles),
        ci_environment_mentions_sklearn=ci_mentions,
        ci_docker_scan_hits=ci_hits,
        environment=env,
        dependency_status=status.value,
        dependency_approval_required=approval_required,
        p8b3_1_may_proceed=may_proceed,
        p8b3_1_proceed_reason=proceed_reason,
        p8b3_0_pass=True,
        notes=notes,
    )
    return result


def _git_commit(project_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def write_audit_json(result: P8B3DependencyAuditResult, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    payload["code_commit"] = _git_commit(Path(result.project_root))
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
