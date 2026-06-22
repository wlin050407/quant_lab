# ML-P8B.3.6 Reduced Feature Set Owner Review

**Date:** 2026-06-21  
**Branch:** `research/zdte-fusion-model`  
**Stage:** ML-P8B.3.6  
**Gate:** **PASS** (documentation review only — no fitting)

**Sources:**

- [`p8b3_5_feature_stability_diagnostics_report.md`](p8b3_5_feature_stability_diagnostics_report.md)
- [`p8b3_4_feature_reduction_stability_diagnostic_plan.md`](p8b3_4_feature_reduction_stability_diagnostic_plan.md)
- [`p8b3_4_feature_governance_rules.md`](p8b3_4_feature_governance_rules.md)
- [`p8b3_3_learned_baseline_result_review.md`](p8b3_3_learned_baseline_result_review.md)
- [`p8b3_2_train_only_fitting_report.md`](p8b3_2_train_only_fitting_report.md)

**Decision record:** [`p8b3_6_reduced_feature_approval_record.md`](p8b3_6_reduced_feature_approval_record.md)  
**Next gate:** [`p8b3_7_reduced_feature_refit_gate.md`](p8b3_7_reduced_feature_refit_gate.md)

---

## Owner Decision

```text
Status: Approved for limited reduced-feature train-only refit planning only
```

This approval authorizes **planning and implementation of ML-P8B.3.7** only. It does **not** authorize hyperparameter search, production backtest, or trading signals.

---

## P8B.3.5 Diagnostic Recap

| Metric | Value |
|--------|-------|
| Input rows | 1391 (1390 baseline-eligible) |
| Raw feature columns | 198 |
| Numeric features analyzed | 180 |
| Train all-NaN features | 4 |
| Train constant features | 22 |
| Train near-constant (≥99%) | 22 |
| High-correlation pairs (\|r\| ≥ 0.95, train) | 225 |
| Correlation clusters | 23 |
| `target_based_selection_used` | **false** |
| `model_fitting_performed` | **false** |
| Selection scope | train-only unsupervised |
| Feature set version | `p8b3_reduced_features_v0_proposal` |

Validation and test splits were used for **monitoring only** — not for feature inclusion/exclusion.

---

## Raw vs Reduced Feature Count

| Stage | Feature count |
|-------|---------------|
| P8B.1 raw catalog columns | 198 |
| P8B.3.2 numeric used (ungoverned) | 168 (after runtime type/all-NaN drop) |
| **FeatureSet_A** (approved primary) | **27** |
| **FeatureSet_B** (approved secondary) | **82** |
| FeatureSet_C (diagnostic only) | 92 |

Reduction ratio (A vs 180 numeric): **85% fewer features** — appropriate given P8B.3.2 severe OOS degradation on the full matrix.

---

## A / B / C Comparison and Approval

| Set | Feature count | Main groups | Intended role | Approval status |
|-----|---------------|-------------|---------------|-----------------|
| **A** | 27 | context, deterministic, index_path, quality | Primary reduced refit candidate | **Approved** |
| **B** | 82 | A groups + quote_microstructure, trade_flow_proxy, greeks_iv | Secondary sensitivity candidate | **Approved secondary** |
| **C** | 92 | all groups (incl. chain_summary, multiresolution) + full prune | Diagnostic reference | **Not approved for first refit** |

### Why FeatureSet_A is primary

- Most **conservative** and **interpretable** set after P8B.3.2 showed severe OOS degradation (P0 Linear test MAE 74.55; P1 test balanced_acc 0.303 vs model-free 0.500).
- Excludes zone-sparse deterministic features and all flow/microstructure groups that add noise risk with 19 sessions.
- 27 features vs 11 train sessions — still high ratio but materially lower than 180:11.
- Aligns with governance priority: quality → context → deterministic → index before sparse/flow features.

### Why FeatureSet_B is secondary sensitivity

- Tests whether **quote / trade / greeks** proxies add signal **after** A is evaluated on the same split and fixed hyperparameters.
- 82 features — meaningful step-up from A but still below ungoverned 168 used in P8B.3.2.
- Approved for **optional** P8B.3.7 sensitivity refit only; not default if A alone is evaluated.

### Why FeatureSet_C is not approved for first refit

- Includes chain_summary and multiresolution groups — highest train missingness (multiresolution mean 0.20).
- Only modestly smaller than B (92 vs 82) while retaining more unstable/sparse groups.
- Useful as **diagnostic reference** in local manifest; not sufficiently conservative for first reduced-feature learned refit given P8B.3.3 negative OOS baseline.

---

## P8B.3.2 Context (Why Conservative)

| Track | P8B.2 test reference | P8B.3.2 full-feature learned (test) |
|-------|----------------------|-------------------------------------|
| P0 MAE | zero_em **2.01** | Ridge 3.65; Linear 74.55 |
| P1 balanced_acc | majority **0.500** | Logistic **0.303** |

Learned models **overfit** on 168 numeric features with 19 sessions. Feature reduction is a prerequisite before any further learned fitting — not a guarantee of improvement.

---

## Train-Only Unsupervised Selection Confirmation

```text
target_based_selection_used = false
model_fitting_performed = false
No validation/test performance used for feature selection
No target correlation used for feature selection
Exclusion reasons recorded per feature in reduced_feature_set_manifest.json (local artifact)
```

---

## Explicit Non-Authorization

```text
This approval does not authorize P8B.4 hyperparameter search.
This approval does not authorize production backtest.
This approval does not authorize trading signals.
P8B.4 / P8B.5 / P8B.6 remain BLOCKED.
```

---

## P8B.3.6 Stage Compliance

| Check | Status |
|-------|--------|
| Model fitting in this stage | **NO** |
| `.fit()` called | **NO** |
| New feature build | **NO** |
| Artifacts committed | **NO** |
| `label_spec.md` modified | **NO** |
| `requirements.txt` modified | **NO** |

---

## Next Stage

```text
ML-P8B.3.7 — Train-Only Reduced-Feature Learned Refit
```

See [`p8b3_7_reduced_feature_refit_gate.md`](p8b3_7_reduced_feature_refit_gate.md).

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial owner review; A primary, B secondary, C not for first refit |

---

**End of review.**
