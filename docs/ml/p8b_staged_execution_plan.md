# ML-P8B — Staged Execution Plan

**Phase:** ML-P8A.1 — Owner Review for P8B Execution Gate  
**Branch:** `research/zdte-fusion-model`  
**Approval:** [`p8b_execution_approval_record.md`](p8b_execution_approval_record.md)  
**Harness plan:** [`p8a_baseline_modeling_harness_plan.md`](p8a_baseline_modeling_harness_plan.md)  
**Eval protocol:** [`p8a_evaluation_protocol.md`](p8a_evaluation_protocol.md)  
**Split protocol:** [`p8a_no_leak_split_protocol.md`](p8a_no_leak_split_protocol.md)

---

## Status

```text
Execution plan for staged P8B preparation (P8B.0–P8B.2 authorized)
P8B.3+ learned model fitting: NOT authorized
No code implementation in P8A.1 — this document defines gates only
```

---

## Overview

P8B is decomposed into sub-stages so that harness infrastructure, feature validation, and model-free evaluation can proceed **without** learned model fitting until a separate owner gate opens P8B.3.

```text
P8B.0  Harness code (metrics, split, validators, manifest)
  ↓ PASS
P8B.1  Feature dataset + strict hash join + leakage validation
  ↓ PASS
P8B.2  Model-free baseline evaluation report
  ↓ PASS → owner review
P8B.3  Simple model fitting          [NOT APPROVED]
P8B.4  Hyperparameter search         [NOT APPROVED]
P8B.5  Production backtest           [NOT APPROVED]
P8B.6  Trading signal generation     [NOT APPROVED]
```

---

## Global Constraints (All Stages)

```text
session-grouped split only — no row-level random split
same trade_date cannot appear in more than one split
features source_timestamp <= as_of_timestamp
labels.* and official_close forbidden in feature matrix
formal label_spec.md unchanged (v1.0.0)
deterministic financial formulas frozen
zone labels remain strict secondary
artifacts not committed to git
no production use
```

---

## P8B.0 — Harness Implementation Only

### Purpose

Implement the evaluation infrastructure defined in P8A without building features or fitting models.

### Allowed

```text
metric functions (P0 MAE/RMSE/..., P1 F1/AUC/..., P2 macro F1/...)
split validators (session-grouped integrity, no cross-split trade_date)
forbidden-input validators (labels.*, official_close, future fields)
run manifest schema (JSON)
evaluation report schema (JSON + markdown summary)
model-free baseline interface (predict without learned weights)
leakage check hooks (reuse quant_lab.ml.leakage patterns)
unit tests on synthetic fixtures
```

### Forbidden

```text
feature full build
joined feature-label dataset production run
model fitting (sklearn or otherwise)
learned coefficient storage
prediction artifacts from learned models
ingest of new dates
modification of label builder or financial formulas
```

### Suggested Code Layout (Future Implementation)

```text
src/quant_lab/ml/harness/
  metrics.py          — P0/P1/P2 metric calculators
  splits.py           — split loader + session validator
  validators.py       — forbidden input + schema guards
  baselines.py        — model-free baseline interfaces
  manifest.py         — run manifest + report schema
  report.py           — evaluation report builder
tests/test_ml_harness_*.py
```

### Acceptance Gate — P8B.0 PASS

```text
✓ unit tests pass
✓ no model fitting in codebase paths exercised
✓ no feature build invoked
✓ split validator catches same-session leakage (negative test)
✓ forbidden input validator catches labels.* / official_close / future fields (negative test)
✓ metrics tested on synthetic data (hand-computed expected values)
✓ run manifest schema documented and validated in tests
✓ ruff pass on new harness modules
✓ full pytest pass
✓ no artifacts committed
```

---

## P8B.1 — Feature Dataset Build + Leakage Validation

### Purpose

Build P7 feature dataset for the P7.8.3 date list and validate strict hash join with v1.1 draft labels.

### Prerequisites

```text
P8B.0 PASS
p8b_execution_approval_record.md P8B.1 authorized
```

### Allowed

```text
build features for P7.8.3 dataset (19 sessions, regular_5min anchors)
strict hash join on (trade_date, as_of_timestamp, replay_state_hash, deterministic_bundle_hash)
timestamp leakage validation (source_timestamp <= as_of)
feature missingness / coverage report
joined dataset manifest (local, gitignore)
reuse existing P7 feature builder — no formula changes
```

### Forbidden

```text
model fitting
hyperparameter tuning
test split evaluation with any learned model
modification of feature formulas or Pin Zone thresholds
ingest of new dates (unless separately authorized)
committing parquet/csv/jsonl to git
```

### Dataset Reference

| Field | Value |
|-------|-------|
| Label source | `artifacts/datasets/pit_sample_baseline_v1_1_validation/` |
| Feature output (proposed) | `artifacts/features/pit_sample_baseline_v1_1_validation/` |
| Joined output (proposed) | `artifacts/datasets/pit_sample_baseline_v1_1_validation_joined/` |
| Dates | 19 (P7.8.3 rebuild list) |
| baseline_label_schema_version | `1.1.0-draft` |
| feature_schema_version | `1.0.0` |

### Acceptance Gate — P8B.1 PASS

```text
✓ feature dataset built for all 19 sessions (or documented failures)
✓ leakage PASS on feature rows
✓ strict hash join PASS (no orphan label/feature rows without documented reason)
✓ no forbidden columns in feature matrix
✓ feature coverage report generated (missingness by group)
✓ joined row count matches label eligible subset expectation (~1390 baseline rows)
✓ manifest records label + feature schema versions and git commit
✓ artifacts not committed
✓ no model fitting performed
```

---

## P8B.2 — Model-Free Baseline Evaluation

### Purpose

Run model-free baselines on session-grouped splits and produce the first harness evaluation report.

### Prerequisites

```text
P8B.1 PASS
p8b_execution_approval_record.md P8B.2 authorized
split manifest created per p8a_no_leak_split_protocol.md
```

### Allowed Baselines

| Track | Baseline | Fit scope |
|-------|----------|-----------|
| P0 | Zero EM (ŷ = 0) | none |
| P0 | Train median d_em | train eligible rows only |
| P0 | Session prior median | train sessions only |
| P1 @ 0.50 | Majority class | train sessions |
| P1 @ 0.50 | Constant not_near | none |
| P1 @ 0.50 | Train prior P(near) | train sessions |
| P1 @ 0.25 | Same trio | train sessions (sensitivity) |
| P2 @ 0.50 | Majority class | train sessions (optional) |

**Disallowed in P8B.2:**

```text
previous-anchor persistence (LEAKAGE-RISK — default off)
any sklearn .fit() call
any learned coefficients
```

### Allowed Outputs

```text
metrics report JSON (train / val / test per p8a_evaluation_protocol.md)
markdown summary report
run manifest with split hash + dataset manifest hash
zone secondary metrics on zone-eligible rows only
```

### Forbidden

```text
sklearn model fitting
learned coefficients
hyperparameter search
threshold tuning on validation for model scores (labels use fixed EM bands)
financial performance claims
test-set-driven iteration / peeking for tuning
committing prediction parquet/csv to git
```

### Acceptance Gate — P8B.2 PASS

```text
✓ metrics report generated for P0, P1 @ 0.50, P1 @ 0.25 (minimum)
✓ train-only priors used; validation/test not used for prior computation
✓ validation/test untouched for tuning
✓ no leakage violations in harness run
✓ no learned model fitting detected in run manifest
✓ session-grouped split integrity verified
✓ P1 0.50 dual class checked in train and validation splits
✓ zone secondary metrics reported separately
✓ artifacts not committed
✓ owner can review report before P8B.3 discussion
```

---

## P8B.3 — Simple Model Fitting

### Status

```text
Not approved in ML-P8A.1.
Requires future owner approval (p8b_model_fitting_approval_record.md).
```

### Would Include (If Approved Later)

```text
linear / ridge regression (P0)
logistic regression (P1)
multinomial logistic regression (P2 optional)
fixed default hyperparameters only (no search in first wave)
beat model-free baselines on validation before test eval
model cards + run manifests
```

### Would Require (If Approved Later)

```text
P8B.0–P8B.2 all PASS
explicit owner sign-off for learned fitting
sklearn dependency verified in requirements.txt
no test tuning
```

---

## P8B.4 — P8B.6 (Not Approved)

| Sub-stage | Scope | Status |
|-----------|-------|--------|
| P8B.4 | Hyperparameter search / AutoML | **BLOCKED** |
| P8B.5 | Production backtest | **BLOCKED** |
| P8B.6 | Trading signal generation | **BLOCKED** |

---

## Master Gate Checklist

| Item | Required | P8A.1 Status |
|------|----------|--------------|
| P7.8.3 dataset validation PASS | Yes | **PASS** |
| P8A harness plan PASS | Yes | **PASS** |
| P8B.0 implementation approval | Yes | **Approved** |
| P8B.1 feature build approval | Yes | **Approved** (after P8B.0) |
| P8B.2 model-free baseline approval | Yes | **Approved** (after P8B.1) |
| P8B.3 learned model fitting approval | For fitting | **Not approved** |
| Feature leakage validation | P8B.1 | Required |
| Session-grouped split | All stages | Required |
| No row-level random split | All stages | Enforced |
| No artifacts committed | All stages | Enforced |
| Formal label_spec unchanged | All stages | Enforced |

---

## Next Stage After P8A.1

```text
ML-P8B.0 — Modeling Harness Implementation
```

Stop conditions: any gate FAIL halts progression; P8B.3 requires new owner approval.

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-20 | Initial staged execution plan (P8B.0–P8B.2) |

---

**End of staged execution plan.**
