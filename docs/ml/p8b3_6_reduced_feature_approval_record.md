# ML-P8B.3.6 Reduced Feature Approval Record

**Date:** 2026-06-21  
**Branch:** `research/zdte-fusion-model`  
**Stage:** ML-P8B.3.6  
**Review:** [`p8b3_6_reduced_feature_owner_review.md`](p8b3_6_reduced_feature_owner_review.md)

---

## Status

```text
Status: Approved for ML-P8B.3.7 reduced-feature train-only refit only
```

---

## Approved Feature Sets

| Set | ID | Features | Role in P8B.3.7 |
|-----|-----|----------|-----------------|
| Primary | `FeatureSet_A_core_stable` | 27 | **Required** train-only refit |
| Secondary | `FeatureSet_B_core_plus_flow` | 82 | **Optional** sensitivity train-only refit |
| Reference only | `FeatureSet_C_diagnostic_full_pruned` | 92 | **Not approved** for P8B.3.7 fitting |

**Manifest reference (local, not committed):**

```text
artifacts/reports/p8b3_feature_stability_diagnostics/reduced_feature_set_manifest.json
feature_set_version: p8b3_reduced_features_v0_proposal
```

---

## Approved Scope (P8B.3.7)

P8B.3.7 **may**:

```text
Load P8B.1 feature artifacts (read-only; no new feature build)
Load P8B.3.5 reduced feature set manifest for FeatureSet_A and FeatureSet_B column lists
Use FeatureSet_A as primary candidate for train-only learned refit
Use FeatureSet_B as secondary sensitivity candidate for train-only learned refit
Reuse the same configured chronological 11/3/5 split as P8B.2 / P8B.3.2
Fit models only on train sessions (11 sessions)
Use train-only preprocessing (SimpleImputer + StandardScaler fit on train only)
Use fixed hyperparameters only (same as P8B.3.2: Ridge alpha=1.0, Logistic C=1.0, threshold=0.5)
Compare metrics against P8B.2 model-free baselines
Compare metrics against P8B.3.2 full-feature learned baselines
Report metrics by train / validation / test separately
Generate run manifest and evaluation report (artifacts not committed)
```

**Models (unchanged from P8B.3.2 approval):**

```text
P0: LinearRegression, Ridge(alpha=1.0)
P1: LogisticRegression(max_iter=1000, class_weight=None, threshold=0.5)
P2: optional — same gate as P8B.3.2 (skip if insufficient classes)
```

---

## Not Approved

```text
FeatureSet_C first-round refit
P8B.4 hyperparameter search
GridSearchCV / RandomizedSearchCV / xgboost / lightgbm / torch
New feature build or re-ingest
Validation/test threshold tuning
Validation/test feature selection
Target-based feature selection
Production backtest (P8B.5)
Trading signal generation (P8B.6)
Using test metrics for model selection
Committing artifacts to git
Modifying docs/ml/label_spec.md
Modifying requirements.txt
```

---

## Preconditions (Must Hold Before P8B.3.7 Execute)

| # | Condition |
|---|-----------|
| 1 | P8B.3.6 PASS (this record committed) |
| 2 | P8B.3.5 reduced manifest present locally |
| 3 | P8B.1 feature + label artifacts present locally |
| 4 | Split validation and forbidden-input validation PASS |
| 5 | `dependency_status = declared_and_importable` (unchanged from P8B.3.0.1) |

---

## Result Interpretation (Binding for P8B.3.7 Review)

See [`p8b3_7_reduced_feature_refit_gate.md`](p8b3_7_reduced_feature_refit_gate.md) § Result Interpretation Rules.

**No P8B.4 approval can be inferred from P8B.3.7 PASS alone.**

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Approve A primary, B secondary; block C first refit; authorize P8B.3.7 planning |

---

**End of approval record.**
