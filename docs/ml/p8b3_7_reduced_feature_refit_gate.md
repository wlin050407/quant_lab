# ML-P8B.3.7 Reduced-Feature Train-Only Refit Gate

**Date:** 2026-06-21  
**Stage:** ML-P8B.3.7 (future — **not started**)  
**Prerequisite:** ML-P8B.3.6 PASS  
**Approval:** [`p8b3_6_reduced_feature_approval_record.md`](p8b3_6_reduced_feature_approval_record.md)  
**Review:** [`p8b3_6_reduced_feature_owner_review.md`](p8b3_6_reduced_feature_owner_review.md)

---

## Stage Definition

```text
ML-P8B.3.7 — Train-Only Reduced-Feature Learned Refit
```

Re-run P8B.3.2-style **train-only** simple learned baselines using **FeatureSet_A** (primary) and **FeatureSet_B** (optional sensitivity), with the same split protocol and fixed hyperparameters. Compare against P8B.2 model-free and P8B.3.2 full-feature learned results.

**P8B.3.6 does not implement P8B.3.7.**

---

## Prerequisites

| # | Prerequisite |
|---|--------------|
| 1 | P8B.3.6 PASS + approval record committed |
| 2 | `reduced_feature_set_manifest.json` from P8B.3.5 (local) |
| 3 | P8B.1 features + labels artifacts (local) |
| 4 | P8B.2 and P8B.3.2 evaluation reports for comparison reference |

---

## Allowed in P8B.3.7

```text
Load P8B.1 feature artifacts (no new feature build)
Load P8B.3.5 reduced feature set manifest (FeatureSet_A, FeatureSet_B column lists)
Train-only .fit() on approved sklearn models (same specs as P8B.3.2)
Train-only SimpleImputer + StandardScaler
Fixed hyperparameters only
Evaluate on train / validation / test (same 11/3/5 split)
Compare vs P8B.2 model-free baselines (test split primary)
Compare vs P8B.3.2 full-feature learned baselines (test split)
Generate p8b3_7_run_manifest.json and evaluation report (local)
Unit tests for train-only / reduced-column gates
```

**Proposed implementation (future):**

```text
config/ml/p8b3_7_reduced_feature_refit.yaml
scripts/run_reduced_feature_learned_refit.py
src/quant_lab/ml/harness/p8b3_7_refit.py
tests/test_p8b3_7_reduced_feature_refit.py
docs/ml/p8b3_7_reduced_feature_refit_report.md
```

---

## Forbidden in P8B.3.7

```text
Hyperparameter search (P8B.4)
GridSearchCV / RandomizedSearchCV
FeatureSet_C fitting
Changing feature columns based on validation/test metrics
Target-based feature selection
Test-set threshold tuning
Test-set model selection
New feature build / ingest
Production backtest (P8B.5)
Trading signal generation (P8B.6)
Modifying label_spec.md or requirements.txt
Committing artifacts to git
```

---

## Feature Sets

| Set | Columns | P8B.3.7 role |
|-----|---------|--------------|
| FeatureSet_A_core_stable | 27 | **Required** primary refit |
| FeatureSet_B_core_plus_flow | 82 | **Optional** sensitivity refit (skip with reason if blocked) |
| FeatureSet_C_diagnostic_full_pruned | 92 | **Forbidden** in P8B.3.7 |

---

## Split and Protocol (Unchanged)

```text
split_protocol: configured chronological 11 / 3 / 5
train_sessions: 11 (2024-01-05 … 2024-10-04)
validation_sessions: 3 (2024-11-01, 2024-11-29, 2024-12-06)
test_sessions: 5 (2025-01-03 … 2025-05-02)
preprocessing_fit_on_train_only: true
test_not_used_for_tuning: true
```

---

## Fixed Hyperparameters (Unchanged from P8B.3.2)

```text
Ridge alpha = 1.0
LogisticRegression C = 1.0, max_iter = 1000, class_weight = None
P1 threshold = 0.5
No hyperparameter search
```

---

## PASS Gate Criteria

ML-P8B.3.7 PASS requires **all**:

```text
[ ] FeatureSet_A refit completed (P0 Linear/Ridge + P1 0.50 Logistic minimum)
[ ] FeatureSet_B sensitivity refit completed OR skipped with documented reason
[ ] FeatureSet_C not fitted
[ ] Train-only preprocessing verified
[ ] Train-only model fitting verified
[ ] Forbidden columns absent from X
[ ] No target columns in X
[ ] Metrics reported by train / validation / test
[ ] Comparison vs P8B.2 model-free baselines documented
[ ] Comparison vs P8B.3.2 full-feature learned baselines documented
[ ] No hyperparameter search
[ ] test_not_used_for_tuning = true in manifest
[ ] target_based_selection_used = false
[ ] Artifacts not committed
[ ] label_spec.md unchanged
[ ] requirements.txt unchanged
[ ] pytest pass
[ ] ruff pass on new/modified code
```

---

## Result Interpretation Rules

These rules apply when reviewing P8B.3.7 outcomes (in P8B.3.7 report or follow-on review):

```text
If FeatureSet_A still fails to beat zero_em / majority baselines on test:
    → Learned modeling remains blocked for progression toward P8B.4
    → Recommend ML-P8C dataset expansion or pause (Option C from P8B.3.3)

If FeatureSet_A improves validation but fails test:
    → Do not tune hyperparameters or features
    → Treat as instability / regime-shift risk; document and stop

If FeatureSet_A improves test but FeatureSet_B fails:
    → Prefer FeatureSet_A; do not expand complexity automatically

If FeatureSet_B improves over FeatureSet_A on test:
    → Require owner review before adopting B as default candidate
    → Does not authorize P8B.4

No P8B.4 approval can be inferred from P8B.3.7 PASS alone.
P8B.3.7 PASS only means the reduced-feature refit protocol executed correctly.
```

---

## Blocked Stages (Unchanged)

```text
P8B.4  hyperparameter search        BLOCKED (unless separate owner approval after P8B.3.7 review)
P8B.5  production backtest          BLOCKED
P8B.6  trading signal generation    BLOCKED
```

---

## After P8B.3.7 (Not Automatic)

| Outcome | Next step |
|---------|-----------|
| A fails test vs P8B.2 | Owner review → dataset expansion (P8C) or pause |
| A passes test vs P8B.2 | Owner review → **still no P8B.4** without explicit approval |
| B beats A on test | Owner review before any default change |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial P8B.3.7 gate per P8B.3.6 owner approval |

---

**End of gate document.**
