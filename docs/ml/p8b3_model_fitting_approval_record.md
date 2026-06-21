# ML-P8B.3 Model Fitting Approval Record

**Phase:** ML-P8B.3 Approval Review — Learned Model Fitting Gate  
**Branch:** `research/zdte-fusion-model`  
**Prior phase:** ML-P8B.2 — Model-Free Baseline Evaluation (`204b14f`)  
**P8B.2 report:** [`p8b2_model_free_baseline_report.md`](p8b2_model_free_baseline_report.md)  
**Implementation plan:** [`p8b3_simple_model_fitting_plan.md`](p8b3_simple_model_fitting_plan.md)  
**Staged plan:** [`p8b_staged_execution_plan.md`](p8b_staged_execution_plan.md)  
**Prior staged approval:** [`p8b_execution_approval_record.md`](p8b_execution_approval_record.md)

---

## Status

```text
Status: Approved for limited simple learned baseline fitting only
```

This approval **does not** authorize hyperparameter search, production backtest, trading signal generation, deep learning, gradient boosting, or any scope outside the sub-stages listed below.

---

## Prerequisites (All PASS)

| Prerequisite | Status |
|--------------|--------|
| P8B.0 harness implementation | **PASS** |
| P8B.1 feature dataset + leakage validation | **PASS** (1391 rows, 198 features, 19 sessions) |
| P8B.2 model-free baseline evaluation | **PASS** (session-grouped 11/3/5, forbidden input PASS) |
| P8A evaluation protocol | **Documented** |
| P8A split protocol | **Documented** |
| Formal `label_spec.md` | **Unchanged** (v1.0.0) |
| Zone labels | **Strict secondary** (not replaced) |

---

## Owner Sign-off

```text
Owner:     Weitong Lin
Date:      2026-06-21
Decision:  Approved for limited simple learned baseline fitting only (P8B.3.0–P8B.3.3)
Notes:     P8B.2 model-free baselines completed; no learned fitting occurred in P8B.2.
           Approved models: LinearRegression / Ridge (P0), LogisticRegression (P1),
           Multinomial LogisticRegression (P2 optional).
           Fixed default hyperparameters only. No test tuning.
           Zone labels remain strict secondary. No production use.
           Dependency: sklearn may be used only per dependency rule below.
```

---

## Approved Sub-Stages

| Sub-stage | Scope | Status |
|-----------|-------|--------|
| **P8B.3.0** | Dependency / environment audit | **Authorized** |
| **P8B.3.1** | Simple learned baseline implementation | **Authorized** (after P8B.3.0 PASS) |
| **P8B.3.2** | Train-only fitting on approved split | **Authorized** (after P8B.3.1 PASS) |
| **P8B.3.3** | Validation/test evaluation with locked protocol | **Authorized** (after P8B.3.2 PASS) |

Execution must follow [`p8b3_simple_model_fitting_plan.md`](p8b3_simple_model_fitting_plan.md).

---

## Approved Learned Models

### P0 — Regression

| Model | Target | Fit scope |
|-------|--------|-----------|
| `LinearRegression` or `Ridge` | `labels.close_distance_to_primary_pin_em` | train sessions only |

Compare against P8B.2 model-free baselines: `zero_em`, `train_median_em`, `train_mean_em`.

### P1 — Binary

| Model | Target | Fit scope |
|-------|--------|-----------|
| `LogisticRegression` | `labels.close_near_primary_pin_050` (primary) | train sessions only |
| `LogisticRegression` | `labels.close_near_primary_pin_025` (sensitivity) | train sessions only |

Fixed decision threshold **0.5** unless separately reported.  
`class_weight` may be used only if pre-declared in run manifest before fitting.

Compare against P8B.2 baselines: `majority_class`, `constant_not_near`, `train_prior_probability`.

### P2 — Optional (not a P8B.3 gate requirement)

| Model | Target | Fit scope |
|-------|--------|-----------|
| `LogisticRegression` (multinomial) | `labels.close_above_below_primary_pin_050` | train sessions only |
| `LogisticRegression` (multinomial) | `labels.close_above_below_primary_pin_025` | train sessions only |

---

## Not Approved

```text
Not approved:
- xgboost
- lightgbm
- torch / deep learning
- hyperparameter search / AutoML
- production backtest
- trading signal generation
- threshold tuning on validation or test scores
- row-level random split
- using test metrics for model selection
- new feature build or ingest
- modifying docs/ml/label_spec.md
- modifying deterministic financial formulas (Pin/GEX/VEX/EM/Valid Exit)
- modifying Pin Zone threshold
- replacing zone labels as primary target
- committing artifacts / raw market data / parquet / csv / jsonl to git
```

---

## Dependency Rule

```text
Use existing dependencies only.
If sklearn is already in the project environment, it may be used.
If sklearn is not already available, stop and request dependency approval.
Do not add new dependency in P8B.3 without owner approval.
Do not modify requirements.txt in P8B.3 without owner approval.
```

**Audit note (P8B.3.0):** As of this approval date, `scikit-learn` is **not** listed in `requirements.txt`. It may be present in the local dev environment, but P8B.3.0 must verify availability and record version. Adding `scikit-learn` to `requirements.txt` requires a separate owner-approved dependency change before P8B.3.1 implementation is considered complete.

---

## Feature / Input Rules

Reuse P8B.1 validated feature dataset only:

```text
artifacts/features/pit_features_baseline_v1_1_validation/
artifacts/datasets/pit_sample_baseline_v1_1_validation/
```

Before every fitting run, re-execute:

```text
validate_session_split()
detect_row_level_random_split()
validate_forbidden_features()
```

Forbidden inputs (unchanged from P8B.2):

```text
official_close
future_return / future_high / future_low
post_as_of_volume / final_daily_volume
label_source_timestamp
labels.*
close_distance_to_primary_pin_em (as feature)
close_near_primary_pin_050 / _025 (as feature)
close_above_below_primary_pin_050 / _025 (as feature)
baseline_target_eligible / baseline_target_exclusion_reasons (as feature)
any label / target field
```

---

## Training Protocol Constraints

```text
fit only on train sessions (baseline_target_eligible rows)
validation used only for model selection / reporting — not for test peeking
test used only once for final locked evaluation
no tuning on test
no row-level random split
no same trade_date across splits
no leakage
```

If standardization / scaling is applied:

```text
fit scaler on train only
apply scaler to validation / test
record scaler parameters in run manifest
```

Default hyperparameters only (no search). Example defaults to be pinned in P8B.3.1:

```text
Ridge: alpha=1.0 (fixed)
LogisticRegression: C=1.0, max_iter=1000, solver per sklearn default for binary/multinomial
```

---

## Metrics and Reporting

P8B.3 reports must include:

```text
model-free baseline metrics from P8B.2 (reference)
learned model metrics
delta vs model-free baselines
train / validation / test separately — never test-only headline
```

See [`p8b3_simple_model_fitting_plan.md`](p8b3_simple_model_fitting_plan.md) for full metric list and acceptance gate.

---

## Run Manifest Requirements

P8B.3 run manifest must include:

```text
stage = ML-P8B.3
model_fitting_allowed = true
model_type
target_name
feature_manifest_hash
dataset_manifest_hash
split_protocol = session_grouped
train_sessions / validation_sessions / test_sessions
dependency_versions (including sklearn if used)
forbidden_input_validation_status
leakage_validation_status
model_free_baseline_reference (P8B.2 report path or hash)
trained_on_sessions_only = true
test_not_used_for_tuning = true
scaler_fitted_on_train_only (if applicable)
hyperparameters (fixed, no search)
```

Local artifacts (gitignored):

```text
artifacts/reports/p8b3_simple_models/
```

---

## P8B.2 Evidence Summary (Context)

```text
joined_rows = 1391
baseline_eligible_rows = 1390
feature_columns = 198
split = chronological 11 / 3 / 5 sessions
forbidden input validation PASS
session-grouped split PASS
no learned model fitting in P8B.2
```

**P0 interpretation correction:** On **test MAE**, `zero_em` (2.01 EM) outperformed `train_median_em` (2.17 EM). On **train MAE**, `train_median_em` (2.04 EM) outperformed `zero_em` (2.16 EM). Validation MAE also favors `zero_em` (3.04 vs 3.19). No claim that train_median is universally better; report splits separately.

---

## Critical Governance Rules

```text
P8B.3 PASS does not authorize production use, backtest, or trading signals.
P8B.3 PASS does not authorize P8B.4+ (hyperparameter search, AutoML).
Learned models are research baselines only until a future gate approves broader scope.
```

---

## Gate Checklist

| Gate | Status |
|------|--------|
| P8B.2 model-free baseline PASS | **PASS** |
| P8B.3 learned model fitting approval | **Approved (limited scope)** |
| P8B.3.0 dependency audit | **Pending** |
| P8B.3.1 implementation | **Blocked until P8B.3.0 PASS** |
| P8B.4 hyperparameter search | **Not approved** |
| P8B.5 production backtest | **Not approved** |
| P8B.6 trading signal | **Not approved** |
| Session-grouped split | **Required** |
| No artifacts committed | **Enforced** |
| Formal label_spec unchanged | **Enforced** |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial P8B.3 limited learned fitting approval |

---

**Status: P8B.3 approved for limited simple learned baseline fitting — implementation blocked until P8B.3.0 dependency audit PASS**
