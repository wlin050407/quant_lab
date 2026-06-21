# ML-P8B.3 Simple Model Fitting Plan

**Phase:** ML-P8B.3 — Simple Learned Baseline Fitting (plan only)  
**Branch:** `research/zdte-fusion-model`  
**Approval record:** [`p8b3_model_fitting_approval_record.md`](p8b3_model_fitting_approval_record.md)  
**P8B.2 report:** [`p8b2_model_free_baseline_report.md`](p8b2_model_free_baseline_report.md)  
**Evaluation protocol:** [`p8a_evaluation_protocol.md`](p8a_evaluation_protocol.md)  
**Split protocol:** [`p8a_no_leak_split_protocol.md`](p8a_no_leak_split_protocol.md)  
**Harness plan:** [`p8a_baseline_modeling_harness_plan.md`](p8a_baseline_modeling_harness_plan.md)

---

## Status

```text
Plan approved — implementation NOT started in this document phase
Approval: p8b3_model_fitting_approval_record.md
model_fitting_allowed: false until P8B.3.1 code stage begins
```

---

## 1. Purpose

Define a **very restricted** learned-model fitting stage that:

1. Reuses P8B.1 validated features and P8B.2 split/manifests.
2. Fits only simple sklearn linear models on **train sessions**.
3. Evaluates on train / validation / test with locked protocol.
4. Compares learned metrics against P8B.2 model-free baselines.
5. Does **not** imply production readiness.

---

## 2. Sub-Stage Breakdown

### P8B.3.0 — Dependency / Environment Audit

**Goal:** Verify sklearn availability and record versions before any `.fit()` call.

| Check | Requirement |
|-------|-------------|
| `import sklearn` | Must succeed in target environment |
| Version record | Write `sklearn.__version__` to run manifest |
| `requirements.txt` | Must not be modified without owner approval |
| New dependencies | **Stop** if sklearn unavailable; request owner approval |

**PASS criteria:**

```text
sklearn importable in execution environment
dependency_versions recorded in audit manifest
no unauthorized dependency file changes
```

**Known gap:** `scikit-learn` is not currently pinned in `requirements.txt`. P8B.3.0 must flag this. Owner-approved addition to `requirements.txt` is required before P8B.3.1 is marked complete.

---

### P8B.3.1 — Simple Learned Baseline Implementation

**Goal:** Implement fitting/evaluation scripts (no hyperparameter search).

Proposed artifacts (future, not in this approval-review phase):

```text
config/ml/p8b3_simple_models.yaml
scripts/run_simple_learned_baselines.py
src/quant_lab/ml/harness/p8b3_fit.py   (or equivalent module)
tests/test_p8b3_simple_models.py
```

**Allowed models:**

| Track | sklearn class | Target |
|-------|---------------|--------|
| P0 | `LinearRegression` or `Ridge(alpha=1.0)` | `labels.close_distance_to_primary_pin_em` |
| P1 primary | `LogisticRegression(C=1.0, max_iter=1000)` | `labels.close_near_primary_pin_050` |
| P1 sensitivity | same | `labels.close_near_primary_pin_025` |
| P2 optional | `LogisticRegression(multi_class='multinomial')` | `labels.close_above_below_primary_pin_*` |

**Forbidden in P8B.3.1:**

```text
xgboost, lightgbm, torch
GridSearchCV, RandomizedSearchCV, Optuna, etc.
feature rebuild, new ingest
any .fit() in tests that reads real artifacts or ThetaData
```

---

### P8B.3.2 — Train-Only Fitting

**Goal:** Fit models on train split only.

```text
Input rows: baseline_target_eligible == true
Split: same 11/3/5 chronological sessions as P8B.2
Fit scope: train sessions only (811 rows in current dataset)
```

Pre-fit gates (must PASS or abort):

```text
validate_session_split()
detect_row_level_random_split()
validate_forbidden_features() on feature column list
```

If scaling:

```text
StandardScaler.fit on X_train only
transform X_val, X_test with train-fitted scaler
record scaler stats in manifest
```

---

### P8B.3.3 — Validation / Test Evaluation

**Goal:** Report metrics with locked protocol; compare to P8B.2 baselines.

```text
validation: report metrics; may inform qualitative review — NOT test tuning
test: single final evaluation; no iterative peeking
report delta vs P8B.2 model-free baselines per split
```

**Model selection rule:**

```text
No model selection on test.
If multiple fixed models are run (e.g. LinearRegression vs Ridge), report all;
do not pick winner based on test performance.
Validation may be used for reporting only in first wave (no HP search).
```

---

## 3. Input Data (Pinned)

```text
Label dataset:  artifacts/datasets/pit_sample_baseline_v1_1_validation/
Feature dataset: artifacts/features/pit_features_baseline_v1_1_validation/
P8B.2 reference: artifacts/reports/p8b2_model_free_baselines/
Output reports:  artifacts/reports/p8b3_simple_models/  (gitignored)
```

**Split (chronological, same as P8B.2):**

| Split | Sessions | Rows (eligible) |
|-------|----------|-----------------|
| train | 11 | ~810 |
| validation | 3 | ~195 |
| test | 5 | ~385 |

Train dates: 2024-01-05 … 2024-10-04  
Validation: 2024-11-01, 2024-11-29, 2024-12-06  
Test: 2025-01-03 … 2025-05-02

---

## 4. Metrics Requirements

### 4.1 Reporting structure

Every report section must show **train / validation / test** columns plus **delta vs P8B.2** model-free baseline.

### 4.2 P0 (regression)

```text
MAE, RMSE, median_absolute_error
sign_accuracy
within_0.25_EM_accuracy
within_0.50_EM_accuracy
outlier_rate (|error| > 3 EM)
```

Reference baselines: `zero_em`, `train_median_em`, `train_mean_em`.

### 4.3 P1 (binary)

```text
class_distribution
balanced_accuracy
precision, recall, F1
Brier score
ROC-AUC (if both classes present)
PR-AUC (if both classes present)
confusion matrix
calibration / ECE (if implemented)
```

Reference baselines: `majority_class`, `constant_not_near`, `train_prior_probability`.

**Class imbalance note:** Train near-ratio ≈ 25.7%. Learned models must not be judged on accuracy alone.

### 4.4 P2 (optional)

```text
macro F1
balanced_accuracy
per-class precision / recall
confusion matrix
class_distribution
```

Not required for P8B.3 gate PASS.

### 4.5 Zone secondary (unchanged)

Report separately on zone-eligible rows only; do not substitute zone targets for baseline primary.

---

## 5. Run Manifest Schema (P8B.3)

Extend P8B.0 `RunManifest` with P8B.3 fields:

```json
{
  "stage": "ML-P8B.3",
  "model_fitting_allowed": true,
  "model_type": "ridge_regression | logistic_regression | ...",
  "target_name": "close_near_primary_pin_050",
  "dataset_manifest_hash": "...",
  "feature_manifest_hash": "...",
  "split_protocol": "session_grouped",
  "train_sessions": ["..."],
  "validation_sessions": ["..."],
  "test_sessions": ["..."],
  "dependency_versions": {
    "sklearn": "...",
    "numpy": "...",
    "pandas": "..."
  },
  "forbidden_input_validation_status": "PASS",
  "leakage_validation_status": "PASS",
  "model_free_baseline_reference": "artifacts/reports/p8b2_model_free_baselines/p8b2_run_manifest.json",
  "trained_on_sessions_only": true,
  "test_not_used_for_tuning": true,
  "hyperparameters": {"Ridge": {"alpha": 1.0}},
  "scaler_fitted_on_train_only": true,
  "artifacts_written": ["artifacts/reports/p8b3_simple_models/"]
}
```

---

## 6. P8B.3 Acceptance Gate Proposal

P8B.3 **PASS** requires all of:

```text
✓ P8B.3.0 dependency audit PASS
✓ session split validation PASS
✓ forbidden input validation PASS
✓ train-only fitting verified (manifest + code audit)
✓ no test tuning (test_not_used_for_tuning = true in manifest)
✓ P0 simple model evaluated (Ridge or LinearRegression)
✓ P1 @ 0.50 LogisticRegression evaluated
✓ model-free baseline comparison reported (delta vs P8B.2)
✓ train / validation / test metrics all reported
✓ run manifest generated
✓ no artifacts committed to git
✓ no production backtest
✓ no trading signal
✓ full pytest PASS
✓ ruff PASS
```

**Not required for PASS:**

```text
P2 multinomial models (optional)
beating model-free baselines on test
calibration / ECE (nice-to-have)
```

**Important:** P8B.3 PASS **does not** mean production-ready or strategy-approved.

---

## 7. Risk Register

| Risk | Mitigation |
|------|------------|
| Test peeking / HP search on test | Fixed hyperparameters; manifest attestation; no search code |
| Label leakage in features | Re-run forbidden validation; reuse P8B.1 dataset only |
| Session leakage | Same split manifest as P8B.2; `detect_row_level_random_split()` |
| Class imbalance (P1) | Report balanced accuracy, PR-AUC; optional pre-declared `class_weight` |
| Overfitting to train | Compare val/test vs P8B.2 baselines; report all splits |
| Dependency drift | P8B.3.0 audit; pin sklearn version in manifest |
| Misinterpretation of P8B.2 P0 | Document: zero_em beats train_median on test MAE |

---

## 8. Explicit Non-Scope

```text
Not in P8B.3:
- production backtest / PnL claims
- trading signal generation
- hyperparameter search (P8B.4)
- new feature engineering
- label_spec merge
- zone label replacement
- xgboost / lightgbm / torch
```

---

## 9. Next Stages After P8B.3 PASS

| Stage | Status |
|-------|--------|
| P8B.3 implementation (P8B.3.0–P8B.3.3) | **Next authorized work** |
| P8B.4 hyperparameter search | **Not approved** |
| P8B.5 production backtest | **Not approved** |
| P8B.6 trading signal | **Not approved** |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial simple model fitting plan (approval review phase) |

---

**Status: Plan approved — await P8B.3.0 dependency audit before implementation**
