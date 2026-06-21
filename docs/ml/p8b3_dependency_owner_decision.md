# ML-P8B.3.0.1 Dependency Owner Decision Record

**Phase:** ML-P8B.3.0.1 — Dependency Owner Decision and Declaration  
**Branch:** `research/zdte-fusion-model`  
**Prior audit:** [`p8b3_dependency_audit_report.md`](p8b3_dependency_audit_report.md)  
**Approval record:** [`p8b3_model_fitting_approval_record.md`](p8b3_model_fitting_approval_record.md)

---

## Owner Decision

```text
Decision: A — Add scikit-learn to formal dependency declaration.
```

| Option | Description | Selected |
|--------|-------------|----------|
| **A** | Add `scikit-learn` to `requirements.txt` | **Yes** |
| B | Treat sklearn as externally provided runtime dependency | No |
| C | Dependency-gated optional code skipping learned fitting | No |

---

## Rationale

```text
P8B.3 learned model fitting requires reproducible dependency availability.
Local environment has sklearn importable, but project dependency files did not declare scikit-learn.
P8B.3.1 should not proceed while dependency_status = importable_but_not_declared.
```

P8B.3.0 audit (2026-06-21) recorded:

```text
sklearn_importable: true (local 1.9.0)
scikit_learn_declared: false
dependency_status: importable_but_not_declared
p8b3_1_may_proceed: false
```

---

## Why B and C Were Rejected (For Now)

### Option B — External runtime dependency

Rejected because:

- `Dockerfile` and `pip install .` path must remain reproducible for research runs.
- External-only sklearn would leave CI/fresh installs without declared dependency.
- Adds operational ambiguity without reducing scope.

### Option C — Dependency-gated optional code

Rejected because:

- P8B.3 scope is explicitly **simple learned baseline fitting** (Ridge / LogisticRegression).
- Optional skip logic would defer the core P8B.3 deliverable rather than unblock it.
- Adds branching complexity before first learned baseline exists.

Option C may be revisited only if a future environment genuinely cannot install scikit-learn.

---

## requirements.txt Change Summary

**File modified:** `requirements.txt` only.

**Added:**

```text
scikit-learn>=1.4          # ML-P8B.3 simple learned baselines (Ridge / LogisticRegression)
```

**Style:** lower-bound (`>=`), consistent with `numpy>=1.26`, `pandas>=2.2`, `scipy>=1.13`.  
**Not pinned** to local version (1.9.0).  
**No lock files** added.  
**Not modified:** `pyproject.toml`, `Dockerfile`, `environment.yml`, lock files.

`pyproject.toml` continues to use `dynamic = ["dependencies"]` from `requirements.txt`.

---

## Expected Audit Result After Rerun

```text
scikit_learn_declared: true
declared_version_spec: scikit-learn>=1.4
dependency_source_files: [requirements.txt]
sklearn_importable: true
dependency_status: declared_and_importable
p8b3_1_may_proceed: true
```

Verified by rerunning:

```bash
python scripts/audit_p8b3_environment.py
```

---

## P8B.3.1 Proceed Condition

```text
If dependency_status = declared_and_importable:
    P8B.3.1 may proceed to limited simple learned baseline implementation.
```

**After P8B.3.0.1:** condition **met** — P8B.3.1 is **authorized to start** (implementation only; no fitting in this phase).

---

## Attestation

- **No model fitting was performed.**
- **No sklearn `.fit()` was called.**
- **No learned model fitting code was implemented.**
- **No artifacts were committed.**

---

## Owner Sign-off

```text
Owner:     Weitong Lin
Date:      2026-06-21
Decision:  A — add scikit-learn to requirements.txt
Notes:     Minimal declaration change only. No lock file. P8B.3.1 may proceed after audit rerun PASS.
```

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Owner decision A recorded; scikit-learn declared in requirements.txt |

---

**Status: P8B.3.0.1 PASS — P8B.3.1 authorized to proceed**
