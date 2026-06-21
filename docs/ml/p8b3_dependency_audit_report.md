# ML-P8B.3.0 Dependency / Environment Audit Report

**Date:** 2026-06-21 (updated post P8B.3.0.1)  
**Branch:** `research/zdte-fusion-model`  
**Stage:** ML-P8B.3.0 / ML-P8B.3.0.1  
**Gate:** **PASS** — `declared_and_importable`; P8B.3.1 may proceed

**Owner decision:** [`p8b3_dependency_owner_decision.md`](p8b3_dependency_owner_decision.md) (Decision A)

---

## Audit Scope

```text
Phase: ML-P8B.3.0 — Dependency / Environment Audit
Follow-up: ML-P8B.3.0.1 — Owner Decision and Declaration
Purpose: Verify scikit-learn declaration and local importability before any learned fitting
Forbidden: model fitting, .fit(), artifact commits
```

**Attestation (P8B.3.0.1):**

- **No model fitting was performed.**
- **No sklearn `.fit()` was called.**
- **`requirements.txt` updated per owner Decision A only.**
- **No artifacts were committed.**

---

## Dependency Files Scanned

| File | Exists | scikit-learn declared | numpy | pandas | scipy |
|------|--------|----------------------|-------|--------|-------|
| `requirements.txt` | Yes | **Yes** (`scikit-learn>=1.4`) | Yes | Yes | Yes |
| `requirements-dev.txt` | No | — | — | — | — |
| `pyproject.toml` | Yes | via dynamic → `requirements.txt` | No | No | No |
| `setup.py` | No | — | — | — | — |
| `setup.cfg` | No | — | — | — | — |
| `environment.yml` | No | — | — | — | — |
| `Pipfile` | No | — | — | — | — |
| `poetry.lock` | No | — | — | — | — |
| `uv.lock` | No | — | — | — | — |

**Additional scans:**

| File | Exists | mentions sklearn |
|------|--------|------------------|
| `Dockerfile` | Yes | No (inherits via `pip install .` → requirements.txt) |
| `.github/workflows/*` | No workflows found | — |

```text
dependency_file_found: true
scikit_learn_declared: true
declared_version_spec: scikit-learn>=1.4
dependency_source_files: [requirements.txt]
lockfile_present: false
ci_environment_mentions_sklearn: false
```

---

## Local Import Results (Rerun 2026-06-21)

| Component | Importable | Version |
|-----------|------------|---------|
| Python | Yes | 3.12.10 |
| numpy | Yes | 2.4.4 |
| pandas | Yes | 3.0.3 |
| scipy | Yes | 1.17.1 |
| sklearn | Yes | **1.9.0** |

```text
sklearn_importable: true
sklearn_version: 1.9.0
```

---

## Declared Dependency Results

```text
numpy>=1.26
pandas>=2.2
scipy>=1.13
scikit-learn>=1.4    # ML-P8B.3 simple learned baselines
```

`pyproject.toml` pulls runtime dependencies dynamically from `requirements.txt`.

---

## dependency_status

```text
dependency_status: declared_and_importable
```

| Status | Meaning |
|--------|---------|
| **`declared_and_importable`** | **Current — declared in requirements.txt AND importable locally** |
| `declared_but_not_importable` | Declared but import fails |
| `importable_but_not_declared` | Previous state (pre P8B.3.0.1) |
| `not_declared_not_importable` | Neither declared nor importable |

---

## Dependency Approval Required

**No — owner Decision A applied.**

Previous P8B.3.0 finding (`importable_but_not_declared`) resolved by adding `scikit-learn>=1.4` to `requirements.txt`.

---

## P8B.3.1 Proceed Rule

| Condition | P8B.3.1 may proceed? |
|-----------|----------------------|
| **`declared_and_importable` (current)** | **Yes** |
| `importable_but_not_declared` | No |
| `declared_but_not_importable` | No — fix environment first |
| `not_declared_not_importable` | No — request dependency approval |

**Current result:** `p8b3_1_may_proceed = true`

---

## What Remains Blocked

```text
P8B.3.2 train-only fitting          (until P8B.3.1 PASS)
P8B.3.3 validation/test eval        (until P8B.3.2 PASS)
P8B.4 hyperparameter search
P8B.5 production backtest
P8B.6 trading signal generation
```

**Unblocked:** P8B.3.1 simple learned baseline implementation (code only; fitting in P8B.3.2).

---

## Artifacts Produced (Not Committed)

```text
artifacts/reports/p8b3_dependency_audit/p8b3_dependency_audit.json
```

Regenerate:

```bash
python scripts/audit_p8b3_environment.py
python scripts/audit_p8b3_environment.py --dry-run
```

---

## Acceptance Gate Summary

| Gate | P8B.3.0 | P8B.3.0.1 |
|------|---------|-----------|
| Dependency files scanned | PASS | PASS |
| sklearn declared | FAIL → | **PASS** |
| sklearn importable | PASS | PASS |
| dependency_status | importable_but_not_declared → | **declared_and_importable** |
| p8b3_1_may_proceed | false → | **true** |
| No model fitting | PASS | PASS |
| No lock files added | PASS | PASS |

---

## Next Stage

```text
ML-P8B.3.1 — Simple Learned Baseline Implementation
```

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial P8B.3.0 audit (importable_but_not_declared) |
| 1.1 | 2026-06-21 | Post P8B.3.0.1 — owner Decision A; declared_and_importable |
