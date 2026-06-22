# ML-P8B.3.5 Diagnostic Implementation Gate

**Date:** 2026-06-21  
**Stage:** ML-P8B.3.5 (future — **not started**)  
**Prerequisite:** ML-P8B.3.4 PASS  
**Plan:** [`p8b3_4_feature_reduction_stability_diagnostic_plan.md`](p8b3_4_feature_reduction_stability_diagnostic_plan.md)  
**Rules:** [`p8b3_4_feature_governance_rules.md`](p8b3_4_feature_governance_rules.md)

---

## 1. Stage Definition

```text
ML-P8B.3.5 — Feature Stability Diagnostics Implementation
```

Compute read-only missingness, stability, correlation, and drift diagnostics on the existing P8B.1 feature matrix; emit reduced feature set **proposals** under train-only governance rules.

**This document is a gate specification only.** P8B.3.4 does not implement P8B.3.5.

---

## 2. Prerequisites (Must Be True Before Starting P8B.3.5)

| # | Prerequisite |
|---|--------------|
| 1 | P8B.3.4 PASS (plan + governance rules committed) |
| 2 | P8B.1 feature artifacts present locally |
| 3 | P8B.3.3 next-gate decision acknowledged (P8B.4 blocked) |
| 4 | Split config matches P8B.2/P8B.3.2 (11/3/5 configured sessions) |
| 5 | Owner aware: diagnostics do not authorize fitting |

---

## 3. Allowed in P8B.3.5

```text
load existing P8B.1 feature artifacts (read-only)
load label dataset for join alignment and eligibility counts only
compute missingness / constant / correlation / stability diagnostics
compute distribution summaries by split and by session (monitoring)
generate diagnostic JSON reports
generate reduced feature set proposal manifest(s) for FeatureSet A/B/C
write run manifest with model_fitting_allowed=false
unit tests for diagnostic functions (no .fit())
```

Proposed implementation locations (future):

```text
config/ml/p8b3_5_feature_diagnostics.yaml
scripts/run_feature_stability_diagnostics.py
src/quant_lab/ml/harness/p8b3_5_diagnostics.py
tests/test_p8b3_5_feature_diagnostics.py
docs/ml/p8b3_5_feature_diagnostics_report.md
```

---

## 4. Forbidden in P8B.3.5

```text
training models
calling .fit() on any estimator (including sklearn unsupervised with fit API — use numpy/pandas stats or fit-free APIs only where possible; if sklearn fit-free unavailable, document exception and get owner approval)
rerunning P8B.3.2 learned fitting
selecting features based on test performance
selecting features based on validation target metrics
selecting features based on full-dataset target correlation
hyperparameter search
production backtest
trading signal generation
new feature build / ingest
modifying label_spec.md or requirements.txt
committing artifacts to git
```

**Note on correlation:** Computing a correlation matrix from train data is allowed; it is not model fitting. Do not use target-aware feature selection wrappers.

---

## 5. Diagnostic Outputs (Required)

| Output | Content |
|--------|---------|
| `p8b3_5_missingness_report.json` | Per-feature and per-group missingness by split |
| `p8b3_5_stability_report.json` | Session-level stability, constant/near-constant flags |
| `p8b3_5_correlation_report.json` | Train-only high-correlation pairs and clusters |
| `p8b3_5_drift_monitoring_report.json` | Val/test distribution summaries (monitoring only) |
| `p8b3_5_reduced_feature_set_proposal.json` | FeatureSet A/B/C proposals per governance manifest schema |
| `p8b3_5_run_manifest.json` | Stage metadata, hashes, `model_fitting_allowed=false` |

Optional: `docs/ml/p8b3_5_feature_diagnostics_report.md` human summary.

---

## 6. PASS Gate Criteria

ML-P8B.3.5 PASS requires **all**:

```text
[ ] diagnostics generated for all dimensions in P8B.3.4 plan
[ ] train-only selection rules applied and recorded in manifest
[ ] validation/test reported as monitoring_only sections only
[ ] reduced feature set proposal created for FeatureSet A, B, C
[ ] exclusion_reasons populated for every excluded feature
[ ] no model fitting performed
[ ] no .fit() called (or documented approved exceptions = none by default)
[ ] no hyperparameter search
[ ] artifacts not committed to git
[ ] docs/ml/label_spec.md unchanged
[ ] requirements.txt unchanged
[ ] tests pass (pytest)
[ ] ruff pass on new/modified code
```

---

## 7. FAIL Conditions

Stop and do not mark PASS if:

```text
any feature selected/excluded using test or validation target metrics
labels used as feature inputs
.fit() called without explicit gate amendment
artifacts committed
split protocol violated (row-level random split)
test sessions used in selection logic
```

---

## 8. After P8B.3.5 PASS (Not Automatic)

P8B.3.5 PASS does **not** unlock P8B.4 or learned re-fit automatically.

| Next step | Gate |
|-----------|------|
| Owner review of reduced feature proposals | Manual |
| Optional P8B.3.x train-only re-fit with reduced features | Separate approval + preconditions from [`p8b3_next_gate_decision.md`](p8b3_next_gate_decision.md) |
| P8B.4 hyperparameter search | **BLOCKED** until owner approval + positive diagnostic review |
| P8C dataset expansion | May proceed in parallel planning; not blocked by P8B.3.5 |

---

## 9. Blocked Stages (Unchanged)

```text
P8B.4  hyperparameter search        BLOCKED
P8B.5  production backtest          BLOCKED
P8B.6  trading signal generation    BLOCKED
```

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial P8B.3.5 implementation gate |

---

**End of gate document.**
