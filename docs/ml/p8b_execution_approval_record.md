# ML-P8B Staged Execution Approval Record

**Phase:** ML-P8A.1 — Owner Review for P8B Execution Gate  
**Branch:** `research/zdte-fusion-model`  
**Prior phase:** ML-P8A — Baseline Modeling Harness Plan (`1d67bda`)  
**Harness plan:** [`p8a_baseline_modeling_harness_plan.md`](p8a_baseline_modeling_harness_plan.md)  
**Staged plan:** [`p8b_staged_execution_plan.md`](p8b_staged_execution_plan.md)  
**Gate proposal:** [`p8b_training_gate_proposal.md`](p8b_training_gate_proposal.md)  
**Dataset evidence:** [`baseline_dataset_rebuild_validation_report.md`](baseline_dataset_rebuild_validation_report.md)

---

## Status

```text
Status: Approved for staged P8B preparation only
```

This approval **does not** authorize learned model fitting (P8B.3+), hyperparameter search, production backtest, or trading signal generation.

---

## Prerequisites (All PASS)

| Prerequisite | Status |
|--------------|--------|
| P7.8.3 dataset validation | **PASS** (1390 eligible / 19 sessions / leakage PASS) |
| P8A harness plan | **PASS** |
| P8A evaluation protocol | **PASS** (documented) |
| P8A split protocol | **PASS** (documented) |
| Formal `label_spec.md` | **Unchanged** (v1.0.0) |

---

## Owner Sign-off

```text
Owner:     Weitong Lin
Date:      2026-06-20
Decision:  Approved for staged P8B preparation only (P8B.0–P8B.2)
Notes:     Harness implementation and feature build may proceed in stages.
           Model-free baseline evaluation authorized after P8B.1 PASS.
           Any learned model fitting requires separate approval after P8B.0–P8B.2 PASS.
           Zone labels remain strict secondary. No production use.
```

---

## Approved Now — Staged Scope

### P8B.0 — Modeling Harness Implementation Only

```text
Approved:
- Implement evaluation harness structure.
- Implement metric calculators (P0 / P1 / P2 / zone secondary).
- Implement split loaders / validators (session-grouped).
- Implement run manifest schema.
- Implement evaluation report schema.
- Implement model-free baseline evaluators (no learned coefficients).
- Implement forbidden-input validators.

Forbidden in P8B.0:
- Feature full build
- Model fitting (any learned parameters)
- Prediction artifacts from learned models
```

### P8B.1 — Feature Dataset Build and Leakage Validation

```text
Approved (after P8B.0 PASS):
- Build feature dataset for P7.8.3 date list (19 sessions).
- Strict hash join labels + features.
- Validate feature timestamps <= as_of_timestamp.
- Feature missingness / coverage report.

Forbidden in P8B.1:
- Model fitting
- Hyperparameter tuning
- Test split evaluation with any learned model
```

### P8B.2 — Model-Free Baseline Evaluation

```text
Approved (after P8B.1 PASS):
- Evaluate majority class baseline (train sessions only).
- Evaluate constant not_near baseline.
- Evaluate train median baseline (P0).
- Evaluate train prior probability baseline (P1).
- Evaluate zero EM baseline (P0).
- Generate metrics report per p8a_evaluation_protocol.md.

Forbidden in P8B.2:
- sklearn model fitting
- Learned coefficients (linear / logistic weights)
- Hyperparameter search
- Financial performance / PnL claims
```

---

## Not Approved Yet

The following require **separate owner approval** after P8B.0–P8B.2 PASS:

```text
Not approved:
- P8B.3 — Simple model fitting
  - linear regression
  - ridge regression
  - logistic regression
  - multinomial logistic regression
  - any sklearn model fitting with learned coefficients

- P8B.4 — Hyperparameter search / AutoML
- P8B.5 — Production backtest
- P8B.6 — Trading signal generation
- Deep learning models
- xgboost / lightgbm / torch (unless dependency separately approved)
- Modifying docs/ml/label_spec.md
- Modifying deterministic financial formulas
- Replacing zone labels
- Row-level random split
- Committing artifacts to git
```

---

## Critical Governance Rule

```text
Any learned model fitting requires a separate owner approval after P8B.0–P8B.2 PASS.
```

P8B.0–P8B.2 approval does **not** auto-unblock P8B.3. A new record (`p8b_model_fitting_approval_record.md`) must be created for P8B.3+.

---

## Gate Checklist

| Gate | Status |
|------|--------|
| P7.8.3 dataset validation PASS | **PASS** |
| P8A harness plan PASS | **PASS** |
| P8B.0 implementation approval | **Approved** (this record) |
| P8B.1 feature build approval | **Approved** (conditional on P8B.0 PASS) |
| P8B.2 model-free baseline approval | **Approved** (conditional on P8B.1 PASS) |
| P8B.3 learned model fitting approval | **Not approved** |
| Feature leakage validation required | **Yes** (P8B.1 gate) |
| Session-grouped split required | **Yes** (all P8B stages) |
| No row-level random split | **Enforced** |
| No artifacts committed | **Enforced** |

---

## Dataset Reference (Pinned)

```text
source config:   config/ml/pit_sample_baseline_v1_1_validation.yaml
rebuild dates:   19 (same as P7.8.3)
row_count:       1391
eligible rows:   1390
sessions:        19
baseline_label_schema_version: 1.1.0-draft
split candidate: train 11 / val 3 / test 5 sessions
```

---

## Rollback

If any P8B stage introduces leakage, same-session split violation, or forbidden-input regression:

1. Halt at failing stage; do not proceed to next sub-stage.
2. Revert harness code if needed; label dataset (P7.8.3) remains valid.
3. This approval remains valid for **re-execution** after fixes; does not auto-approve P8B.3.

---

## Phase Progression

| Phase | Scope | Authorization |
|-------|-------|---------------|
| ML-P8A | Harness plan | **PASS** |
| **ML-P8A.1** | Staged P8B execution approval (this document) | **Complete** |
| **ML-P8B.0** | Harness implementation | **Authorized** |
| **ML-P8B.1** | Feature build + join validation | **Authorized after P8B.0 PASS** |
| **ML-P8B.2** | Model-free baseline eval | **Authorized after P8B.1 PASS** |
| ML-P8B.3 | Simple model fitting | **BLOCKED** |
| ML-P8B.4+ | Search / production / signals | **BLOCKED** |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-20 | Initial staged P8B preparation approval (P8B.0–P8B.2 only) |

---

**End of execution approval record.**
