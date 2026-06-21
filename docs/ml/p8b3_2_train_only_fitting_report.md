# ML-P8B.3.2 Train-Only Simple Learned Fitting Report

**Date:** 2026-06-21  
**Branch:** `research/zdte-fusion-model`  
**Stage:** ML-P8B.3.2  
**Gate:** **PASS**

---

## Summary

First authorized **train-only** `.fit()` stage completed. Six fixed-hyperparameter sklearn models were fitted **only on 11 training sessions**, evaluated on train / validation / test, and compared against P8B.2 model-free baselines. No hyperparameter search, no test tuning, no backtest, no trading signal.

**Attestation:**

- Model fitting was performed only on training sessions.
- No hyperparameter search was performed.
- No test tuning was performed.
- No production backtest was performed.
- No trading signal was generated.

---

## Input Dataset Summary

| Field | Value |
|-------|-------|
| Labels | `artifacts/datasets/pit_sample_baseline_v1_1_validation/` |
| Features | `artifacts/features/pit_features_baseline_v1_1_validation/` |
| Rows | 1391 |
| Baseline-eligible rows | 1390 |
| Feature columns (raw) | 198 |
| Sessions | 19 |
| Split | configured chronological 11 / 3 / 5 (same as P8B.2) |

No re-ingest. No re-feature-build.

---

## Split Sessions

| Split | Sessions |
|-------|----------|
| Train (11) | 2024-01-05, 2024-01-19, 2024-02-13, 2024-03-08, 2024-04-05, 2024-05-03, 2024-06-07, 2024-07-03, 2024-08-02, 2024-09-06, 2024-10-04 |
| Validation (3) | 2024-11-01, 2024-11-29, 2024-12-06 |
| Test (5) | 2025-01-03, 2025-02-07, 2025-03-07, 2025-04-04, 2025-05-02 |

**Split validation:** PASS (`validate_session_split`, `detect_row_level_random_split`)  
**Forbidden input validation:** PASS (`validate_forbidden_features`)  
**P1 0.50 dual-class gate:** PASS (both classes in train and validation)

Validation/test were **not** used for model selection or threshold tuning.

---

## Dependency Status

```text
dependency_status: declared_and_importable
scikit-learn: 1.9.0
numpy: 2.4.4
pandas: 3.0.3
scipy: 1.17.1
python: 3.12.10
```

`requirements.txt` **unchanged** in this stage.

---

## Preprocessing Summary

| Step | Policy |
|------|--------|
| Feature selection | Numeric columns from train rows only |
| Excluded non-numeric | 18 columns (session_status, time_bucket, zone strings, etc.) |
| All-NaN train columns dropped | 12 columns |
| Numeric features used | 168 |
| Imputer | `SimpleImputer(strategy=median)` — **fit on train only** |
| Scaler | `StandardScaler` — **fit on train only** |
| Train fit rows | 810 |

---

## Models Fitted

| Spec | Track | Status |
|------|-------|--------|
| `p0_linear_regression` | P0 | Fitted |
| `p0_ridge_regression` | P0 | Fitted |
| `p1_logistic_050` | P1 primary | Fitted |
| `p1_logistic_025` | P1 sensitivity | Fitted |
| `p2_multinomial_050` | P2 optional | Fitted |
| `p2_multinomial_025` | P2 optional | Fitted |

### Fixed Hyperparameters

```text
Ridge alpha = 1.0
LogisticRegression C = 1.0, max_iter = 1000, class_weight = None
P1 threshold = 0.5 (fixed, no validation tuning)
P2: LogisticRegression + solver=lbfgs (sklearn 1.9 removed multi_class param; lbfgs handles multiclass)
```

---

## P0 Metrics (close_distance_to_primary_pin_em)

### p0_linear_regression

| Split | MAE | RMSE | Median AE | Sign acc | within 0.25 EM | within 0.50 EM |
|-------|-----|------|-----------|----------|----------------|----------------|
| train | 0.895 | 1.561 | 0.627 | 0.825 | 0.220 | 0.417 |
| validation | 11.459 | 12.995 | 11.738 | 0.656 | 0.000 | 0.000 |
| test | 74.553 | 131.697 | 16.861 | 0.613 | 0.003 | 0.005 |

### p0_ridge_regression (alpha=1.0)

| Split | MAE | RMSE | Median AE | Sign acc | within 0.25 EM | within 0.50 EM |
|-------|-----|------|-----------|----------|----------------|----------------|
| train | 0.866 | 1.652 | 0.584 | 0.827 | 0.212 | 0.432 |
| validation | 4.142 | 4.820 | 4.118 | 0.933 | 0.031 | 0.046 |
| test | 3.652 | 5.036 | 3.069 | 0.569 | 0.034 | 0.065 |

---

## P1 0.50 Metrics (close_near_primary_pin_050)

| Split | Balanced acc | Precision | Recall | F1 | Brier | ROC-AUC | PR-AUC | near ratio |
|-------|--------------|-----------|--------|-----|-------|---------|--------|------------|
| train | 0.967 | 0.961 | 0.947 | 0.954 | 0.020 | 0.994 | 0.984 | 25.7% |
| validation | 0.754 | 0.292 | 0.969 | 0.449 | 0.299 | 0.885 | 0.636 | 16.4% |
| test | 0.303 | 0.094 | 0.266 | 0.139 | 0.603 | 0.257 | 0.147 | 20.5% |

Train shows strong fit; test generalization is poor (ROC-AUC 0.26 < 0.5).

---

## P1 0.25 Sensitivity Metrics

| Split | Balanced acc | Precision | Recall | F1 | near ratio |
|-------|--------------|-----------|--------|-----|------------|
| train | 0.999 | 0.996 | 0.996 | 0.996 | 13.7% |
| validation | 0.698 | 0.008 | 1.000 | 0.017 | 0.5% |
| test | 0.282 | 0.000 | 0.000 | — | 9.6% |

Sensitivity only — not a primary gate.

---

## P2 Optional Metrics

### p2_multinomial_050

| Split | Macro F1 | Balanced acc | Class dist (below/near/above) |
|-------|----------|--------------|-------------------------------|
| train | 0.994 | 0.994 | 164 / 208 / 438 |
| validation | 0.745 | 0.798 | 89 / 32 / 74 |
| test | 0.335 | 0.307 | 171 / 79 / 135 |

### p2_multinomial_025

| Split | Macro F1 | Balanced acc | Class dist (below/near/above) |
|-------|----------|--------------|-------------------------------|
| train | 1.000 | 1.000 | 195 / 114 / 501 |
| validation | 0.447 | 0.690 | 119 / 1 / 75 |
| test | 0.540 | 0.475 | 198 / 37 / 150 |

Both P2 models fitted (train had sufficient classes). sklearn 1.9: `multi_class` deprecated/removed; `solver=lbfgs` used.

---

## Comparison vs P8B.2 Model-Free Baselines (test split)

Reference: `artifacts/reports/p8b2_model_free_baselines/p8b2_evaluation_report.json`

### P0 test MAE

| Model | Test MAE | vs zero_em (2.01) | vs train_median_em (2.17) |
|-------|----------|-------------------|---------------------------|
| P8B.2 zero_em | 2.01 | — | better |
| P8B.2 train_median_em | 2.17 | worse | — |
| Learned Linear | 74.55 | +72.55 | +72.38 |
| Learned Ridge | 3.65 | +1.65 | +1.48 |

**Ridge beats unregularized Linear** but **both learned P0 models lose to zero_em** on test MAE.

### P1 0.50 test balanced_accuracy

| Model | Test balanced_accuracy |
|-------|------------------------|
| P8B.2 majority_class | 0.500 |
| P8B.2 constant_not_near | 0.500 |
| P8B.2 train_prior_probability | 0.500 |
| Learned LogisticRegression | 0.303 |

Learned P1 **underperforms** all P8B.2 binary baselines on test balanced accuracy.

---

## Dry-Run and Execute Results

```bash
python scripts/run_simple_learned_baselines.py \
  --config config/ml/p8b3_simple_learned_baselines.yaml --dry-run
# exit 0, p8b3_2_pass=true, model_fitting_performed=false

python scripts/run_simple_learned_baselines.py \
  --config config/ml/p8b3_simple_learned_baselines.yaml --execute
# exit 0, p8b3_2_pass=true, model_fitting_performed=true
```

---

## Run Manifest Summary

Path: `artifacts/reports/p8b3_simple_models/p8b3_2_run_manifest.json` (not committed)

Key fields:

```text
stage: ML-P8B.3.2
model_fitting_allowed: true
preprocessing_fit_on_train_only: true
trained_on_sessions_only: true
test_not_used_for_tuning: true
hyperparameter_search_performed: false
forbidden_input_validation_status: PASS
leakage_validation_status: PASS
```

Evaluation report: `artifacts/reports/p8b3_simple_models/p8b3_2_evaluation_report.json` (not committed)

---

## Implemented Artifacts (code)

| Path | Purpose |
|------|---------|
| `src/quant_lab/ml/harness/p8b3_fit.py` | Train-only fitting, preprocessing, metrics, manifest |
| `scripts/run_simple_learned_baselines.py` | CLI `--dry-run` / `--execute` |
| `tests/test_p8b3_train_only_fitting.py` | Train-only fit gate tests |
| `config/ml/p8b3_simple_learned_baselines.yaml` | Updated stage comment |
| `src/quant_lab/ml/harness/manifests.py` | `HARNESS_STAGE_P8B3_2` |

P8B.3.1 script `prepare_simple_learned_baselines.py` unchanged — still blocks `--execute`.

---

## Tests and Lint

```bash
python -m pytest -q tests/test_p8b3_train_only_fitting.py   # PASS
python -m pytest -q tests/test_p8b3_learned_model_harness.py # PASS
python -m pytest -q tests/test_p8b2_model_free_baselines.py  # PASS
python -m pytest -q                                          # PASS (full suite)
python -m ruff check src/quant_lab/ml/harness/p8b3_fit.py ... # PASS
```

---

## Compliance Attestation

| Check | Status |
|-------|--------|
| dependency declared_and_importable | PASS |
| split validation | PASS |
| forbidden input validation | PASS |
| preprocessing fit on train only | PASS |
| P0 Linear/Ridge fitted train only | PASS |
| P1 0.50 Logistic fitted train only | PASS |
| P1 0.25 sensitivity fitted | PASS |
| P2 optional fitted | PASS |
| metrics by train/val/test | PASS |
| comparison vs P8B.2 reported | PASS |
| no hyperparameter search | PASS |
| no test tuning | PASS |
| no backtest / trading signal | PASS |
| run manifest generated | PASS |
| artifacts not committed | PASS |
| docs/ml/label_spec.md unchanged | PASS |
| requirements.txt unchanged | PASS |

---

## Next Stage Recommendation

```text
ML-P8B.3.3 — Learned Baseline Result Review and Next-Gate Decision
```

P8B.3.2 PASS establishes a **reference learned baseline** only. Test metrics show severe overfitting / poor OOS performance — review in P8B.3.3 before any further modeling stages. **Do not proceed to P8B.4.**

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial P8B.3.2 train-only fitting report |

---

**End of report.**
