# ML-P8B.3.1 Simple Learned Baseline Implementation Report

**Date:** 2026-06-21  
**Branch:** `research/zdte-fusion-model`  
**Stage:** ML-P8B.3.1  
**Gate:** **PASS** (harness only — no fitting)

---

## Summary

Implemented a **fail-closed, dry-run-only** simple learned baseline harness. Model specs, dependency gate, feature/target validation, preprocessing plan metadata, and fit plan JSON generation are in place. **No model fitting occurred.**

---

## Implemented Modules

| Module | Purpose |
|--------|---------|
| `src/quant_lab/ml/harness/learned_models.py` | P0/P1/P2 model spec dataclasses (metadata only) |
| `src/quant_lab/ml/harness/p8b3_plan.py` | Dependency gate, matrix validation, preprocessing plan, fit plan builder |
| `scripts/prepare_simple_learned_baselines.py` | CLI (dry-run default; `--execute` blocked) |
| `config/ml/p8b3_simple_learned_baselines.yaml` | P8B.3.1 configuration |
| `tests/test_p8b3_learned_model_harness.py` | Unit + CLI tests (no `.fit()`) |

Updated: `src/quant_lab/ml/harness/manifests.py` (`HARNESS_STAGE_P8B3_1` in `NO_FITTING_STAGES`), `__init__.py`.

---

## Allowed Model Specs

| Spec | Track | Target |
|------|-------|--------|
| `p0_linear_regression` | P0 | `labels.close_distance_to_primary_pin_em` |
| `p0_ridge_regression` | P0 | `labels.close_distance_to_primary_pin_em` (alpha=1.0) |
| `p1_logistic_050` | P1 | `labels.close_near_primary_pin_050` |
| `p1_logistic_025` | P1 | `labels.close_near_primary_pin_025` (sensitivity) |
| `p2_multinomial_050` | P2 optional | `labels.close_above_below_primary_pin_050` |
| `p2_multinomial_025` | P2 optional | `labels.close_above_below_primary_pin_025` |

Estimators referenced as **strings only** (no sklearn class instantiation in P8B.3.1).

---

## Dependency Gate

```text
dependency_status: declared_and_importable
scikit_learn_declared: true (requirements.txt scikit-learn>=1.4)
sklearn_importable: true
```

Helpers: `check_sklearn_available()`, `get_sklearn_versions()`, `validate_sklearn_dependency_declared()`.

---

## Dry-Run Behavior

Default CLI path builds fit plan without fitting:

```bash
python scripts/prepare_simple_learned_baselines.py --dry-run
python scripts/prepare_simple_learned_baselines.py --check-dependencies
```

`--execute` returns exit code 2:

```text
P8B.3.2 approval required before model fitting execution.
```

Local artifact (gitignored): `artifacts/reports/p8b3_simple_models/p8b3_1_fit_plan.json`

**Dry-run result (2026-06-21):**

```text
p8b3_1_pass: true
fit_execution_status: blocked_until_p8b3_2
model_fitting_allowed: false
baseline_eligible_rows: 1390 (when artifacts present)
feature_columns: 198
```

---

## Feature / Target Validation

`validate_feature_target_matrix()` checks:

- Row counts > 0, baseline-eligible filter
- `validate_forbidden_features()` on feature columns
- Target columns not in X
- `validate_session_split()` + `detect_row_level_random_split()`
- Numeric vs non-numeric column classification
- NaN / inf counts, constant feature detection (train split)

---

## Preprocessing Plan

Metadata only (no scaler fit):

- `StandardScalerPlan` — fit on train only in P8B.3.2
- `NoScalerPlan`
- `NumericFeatureSelectionPlan` — excludes non-numeric columns

---

## Run Manifest Plan

```json
{
  "stage": "ML-P8B.3.1",
  "model_fitting_allowed": false,
  "model_type": "simple_learned_baseline_plan",
  "p8b3_2_required_before_fit": true,
  "fit_execution_status": "blocked_until_p8b3_2"
}
```

---

## No-Fit Attestation

- **No model fitting was performed.**
- **No sklearn `.fit()` was called.**
- **No learned predictions were generated.**
- **P8B.3.2 is required before fitting execution.**

---

## Tests & Ruff

| Suite | Result |
|-------|--------|
| `tests/test_p8b3_learned_model_harness.py` | 15 passed |
| Full pytest | 717 passed |
| Ruff | All checks passed |

---

## P8B.3.2 Prerequisites

Before train-only fitting:

1. P8B.3.1 PASS (this stage)
2. Execute `prepare_simple_learned_baselines.py` with P8B.3.2 approval path
3. Fit scaler on train only; transform val/test
4. Fit Ridge / LogisticRegression on train sessions only
5. Compare metrics vs P8B.2 model-free baselines

---

## Next Stage

```text
ML-P8B.3.2 — Train-Only Simple Learned Fitting
```

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial P8B.3.1 harness implementation report |
