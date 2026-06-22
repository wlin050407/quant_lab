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

**Status: PASS** — see [`p8b0_modeling_harness_implementation_report.md`](p8b0_modeling_harness_implementation_report.md).

**Next authorized stage:** ML-P8B.1 — Feature Dataset Build and Leakage Validation

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

**Status: PASS** — see [`p8b1_feature_dataset_validation_report.md`](p8b1_feature_dataset_validation_report.md).

**Status: PASS** — see [`p8b2_model_free_baseline_report.md`](p8b2_model_free_baseline_report.md).

**Next authorized stage:** ML-P8B.3.0 — Dependency / Environment Audit (see [`p8b3_model_fitting_approval_record.md`](p8b3_model_fitting_approval_record.md))

---

## P8B.3 — Simple Learned Model Fitting

### Status

```text
APPROVED for limited simple learned baseline fitting only (2026-06-21)
P8B.3.0 dependency audit: PASS (2026-06-21) — see p8b3_dependency_audit_report.md
P8B.3.0.1 owner decision: Decision A — scikit-learn declared in requirements.txt
dependency_status: declared_and_importable
P8B.3.1: PASS (2026-06-21) — see p8b3_1_simple_learned_baseline_implementation_report.md
P8B.3.2: PASS (2026-06-21) — see p8b3_2_train_only_fitting_report.md
P8B.3.3: PASS (2026-06-21) — see p8b3_3_learned_baseline_result_review.md, p8b3_next_gate_decision.md
P8B.3.4: PASS (2026-06-21) — see p8b3_4_feature_reduction_stability_diagnostic_plan.md
P8B.3.5: PASS (2026-06-21) — see p8b3_5_feature_stability_diagnostics_report.md
P8B.3.6: PASS (2026-06-21) — see p8b3_6_reduced_feature_owner_review.md, p8b3_6_reduced_feature_approval_record.md
Approval record: p8b3_model_fitting_approval_record.md
Implementation plan: p8b3_simple_model_fitting_plan.md
```

### Approved Sub-Stages

```text
P8B.3.0 — dependency / environment audit          PASS (2026-06-21)
P8B.3.0.1 — owner dependency declaration           PASS (2026-06-21, Decision A)
P8B.3.1 — simple learned baseline implementation  PASS (2026-06-21)
P8B.3.2 — train-only fitting on approved split    PASS (2026-06-21)
P8B.3.3 — learned baseline result review          PASS (2026-06-21)
P8B.3.4 — feature reduction diagnostic plan       PASS (2026-06-21)
P8B.3.5 — feature stability diagnostics impl.       PASS (2026-06-21)
P8B.3.6 — reduced feature set owner review        PASS (2026-06-21)
P8B.3.7 — reduced-feature train-only refit         PASS (A + B sensitivity)
P8B.3.8 — reduced feature refit result review      PASS (2026-06-22)
P8C.0  — controlled expansion plan                  PASS (2026-06-22)
P8C.1  — candidate date selection / ingest plan     AUTHORIZED
P8C.2  — actual controlled ingest                   BLOCKED (owner approval required)
P8C.3  — dataset + feature build validation         BLOCKED
P8C.4  — FeatureSet_A locked refit (expanded)       BLOCKED (fixed hyperparams only)
P8C.5  — expanded result review                     BLOCKED
P8B.4  — hyperparameter search                    BLOCKED
P8B.5  — production backtest                      BLOCKED
P8B.6  — trading signal generation                BLOCKED
```

### Approved Models

```text
P0: LinearRegression or Ridge → close_distance_to_primary_pin_em
P1: LogisticRegression → close_near_primary_pin_050 (primary), _025 (sensitivity)
P2: Multinomial LogisticRegression (optional, not gate-required)
```

### Not Approved

```text
xgboost, lightgbm, torch, hyperparameter search
production backtest, trading signal generation
threshold tuning on validation/test
test metrics for model selection
```

---

## P8B.2 — Model-Free Baseline Evaluation

### Status

```text
PASS (2026-06-21)
Joined rows: 1391 | Baseline-eligible: 1390 | Feature columns: 198
Split: chronological 11/3/5 sessions
Split validation: PASS | Forbidden input: PASS
model_fitting_allowed: false | sklearn .fit(): not called
```

See [`p8b2_model_free_baseline_report.md`](p8b2_model_free_baseline_report.md) and `artifacts/reports/p8b2_model_free_baselines/` (gitignored).

**P0 documentation note:** On test MAE, `zero_em` outperforms `train_median_em`; report splits separately.

---

## P8B.2 (Historical Spec) — Model-Free Baseline Evaluation

### Purpose (original)

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

**Result: PASS** (2026-06-21)

---

## P8B.3 (Historical Spec — Pre-Approval)

Superseded by approved scope above. Original P8A.1 text retained for audit trail:

```text
Previously: Not approved in ML-P8A.1.
Now: Approved for limited simple learned fitting — see p8b3_model_fitting_approval_record.md
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
| P8B.3 learned model fitting approval | For fitting | **Approved (limited scope)** |
| Feature leakage validation | P8B.1 | Required |
| Session-grouped split | All stages | Required |
| No row-level random split | All stages | Enforced |
| No artifacts committed | All stages | Enforced |
| Formal label_spec unchanged | All stages | Enforced |

---

## Next Stage

```text
ML-P8C.1 — Expansion Candidate Selection and Ingest Plan
```

See [`p8c1_expansion_implementation_gate.md`](p8c1_expansion_implementation_gate.md). P8B.4 remains blocked. No ingest until P8C.2 owner approval.

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-20 | Initial staged execution plan (P8B.0–P8B.2) |
| 1.1 | 2026-06-21 | P8B.2 PASS recorded |
| 1.2 | 2026-06-21 | P8B.3 limited learned fitting approval |
| 1.3 | 2026-06-21 | P8B.3.0 dependency audit PASS |
| 1.4 | 2026-06-21 | P8B.3.0.1 owner Decision A; declared_and_importable |
| 1.5 | 2026-06-21 | P8B.3.1 learned model harness PASS |
| 1.6 | 2026-06-21 | P8B.3.2 train-only learned fitting PASS |
| 1.7 | 2026-06-21 | P8B.3.3 result review PASS; P8B.4–P8B.6 blocked; P8B.3.4 authorized |
| 1.8 | 2026-06-21 | P8B.3.4 feature reduction diagnostic plan PASS; P8B.3.5 authorized |
| 1.9 | 2026-06-21 | P8B.3.5 feature stability diagnostics PASS; P8B.3.6 authorized |
| 2.0 | 2026-06-21 | P8B.3.6 owner review PASS; FeatureSet A/B approved; P8B.3.7 authorized |
| 2.1 | 2026-06-22 | P8B.3.7 reduced-feature refit PASS; P8B.3.8 authorized |
| 2.2 | 2026-06-22 | P8B.3.8 result review PASS; FeatureSet_A provisional; P8C planning authorized |
| 2.3 | 2026-06-22 | P8C.0 controlled expansion plan PASS; P8C.1 authorized |

---

**End of staged execution plan.**
