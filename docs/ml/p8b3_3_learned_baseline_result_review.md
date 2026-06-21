# ML-P8B.3.3 Learned Baseline Result Review

**Date:** 2026-06-21  
**Branch:** `research/zdte-fusion-model`  
**Base commit (P8B.3.2):** `1713a028794d5d63bcdc4b981766e81bd5c6c966`  
**Stage:** ML-P8B.3.3  
**Gate:** **PASS** (documentation review only — no fitting)

**Sources reviewed:**

- [`p8b3_2_train_only_fitting_report.md`](p8b3_2_train_only_fitting_report.md)
- [`p8b2_model_free_baseline_report.md`](p8b2_model_free_baseline_report.md)
- [`p8b3_simple_model_fitting_plan.md`](p8b3_simple_model_fitting_plan.md)
- [`p8b3_model_fitting_approval_record.md`](p8b3_model_fitting_approval_record.md)
- [`p8a_evaluation_protocol.md`](p8a_evaluation_protocol.md)
- [`p8a_no_leak_split_protocol.md`](p8a_no_leak_split_protocol.md)

---

## 1. Input / Protocol Recap

| Field | Value |
|-------|-------|
| Dataset | `artifacts/datasets/pit_sample_baseline_v1_1_validation/` |
| Features | `artifacts/features/pit_features_baseline_v1_1_validation/` |
| Rows | 1391 (1390 baseline-eligible) |
| Feature columns (raw) | 198 |
| Numeric features used in fitting | 168 (18 non-numeric excluded; 12 all-NaN train columns dropped) |
| Sessions | 19 |
| Split | session-grouped chronological **11 / 3 / 5** (configured; same as P8B.2) |

### Split dates

| Split | Sessions |
|-------|----------|
| Train (11) | 2024-01-05 … 2024-10-04 |
| Validation (3) | 2024-11-01, 2024-11-29, 2024-12-06 |
| Test (5) | 2025-01-03 … 2025-05-02 |

### Models fitted (P8B.3.2)

| Spec | Target |
|------|--------|
| `p0_linear_regression` | `labels.close_distance_to_primary_pin_em` |
| `p0_ridge_regression` | `labels.close_distance_to_primary_pin_em` |
| `p1_logistic_050` | `labels.close_near_primary_pin_050` |
| `p1_logistic_025` | `labels.close_near_primary_pin_025` (sensitivity) |
| `p2_multinomial_050` | `labels.close_above_below_primary_pin_050` |
| `p2_multinomial_025` | `labels.close_above_below_primary_pin_025` |

### Fixed hyperparameters

```text
Ridge alpha = 1.0
LogisticRegression C = 1.0, max_iter = 1000, class_weight = None
P1 decision threshold = 0.5 (fixed; no validation/test tuning)
P2: LogisticRegression + solver=lbfgs (sklearn 1.9; no multi_class param)
```

### Protocol attestation

```text
Train-only fitting: YES (810 train rows; imputer/scaler fit on train only)
Hyperparameter search: NO
Test tuning / model selection on test: NO
Production backtest: NO
Trading signal generation: NO
```

---

## 2. P0 Review — Regression (`close_distance_to_primary_pin_em`)

### Test-split MAE comparison

| Model | Test MAE | Test RMSE | vs P8B.2 zero_em (2.01) |
|-------|----------|-----------|-------------------------|
| P8B.2 **zero_em** | **2.01** | 3.48 | — (best) |
| P8B.2 train_median_em | 2.17 | 3.60 | +0.16 |
| P8B.2 train_mean_em | 2.32 | 3.72 | +0.31 |
| P8B.3.2 **Ridge** (α=1.0) | 3.65 | 5.04 | +1.64 |
| P8B.3.2 **LinearRegression** | 74.55 | 131.70 | +72.54 |

### Train vs test degradation (learned)

| Model | Train MAE | Validation MAE | Test MAE | Train→Test ratio |
|-------|-----------|----------------|----------|------------------|
| LinearRegression | 0.89 | 11.46 | 74.55 | ~84× |
| Ridge | 0.87 | 4.14 | 3.65 | ~4.2× |

### Conclusions (required)

1. **On test MAE, no learned P0 model beat `zero_em`.**
2. **Unregularized LinearRegression is unstable / unusable** under the current feature/sample regime (catastrophic validation/test blow-up despite low train MAE).
3. **Ridge is materially safer than LinearRegression** (validation MAE 4.14 vs 11.46; test MAE 3.65 vs 74.55) **but still worse than `zero_em` on test** (+1.64 MAE).

P8B.2 already established that `zero_em` beats `train_median_em` on test (2.01 vs 2.17). Learned linear models did not improve on that reference.

---

## 3. P1 Review — Binary Primary (`close_near_primary_pin_050`)

### Test-split comparison

| Model | Test balanced_acc | Test ROC-AUC | Test Brier | Test F1 |
|-------|-------------------|--------------|------------|---------|
| P8B.2 majority_class | **0.500** | — | — | — |
| P8B.2 constant_not_near | **0.500** | — | — | — |
| P8B.2 train_prior_probability | **0.500** | 0.241 | 0.166 | — |
| P8B.3.2 LogisticRegression | **0.303** | **0.257** | 0.603 | 0.139 |

### Train vs test (learned)

| Split | balanced_acc | ROC-AUC | near ratio |
|-------|--------------|---------|------------|
| train | 0.967 | 0.994 | 25.7% |
| validation | 0.754 | 0.885 | 16.4% |
| test | 0.303 | 0.257 | 20.5% |

Validation shows high recall (0.969) but low precision (0.292) — aggressive near predictions that do not generalize.

### Conclusions (required)

1. **LogisticRegression overfit strongly:** train balanced_acc 0.967 → test 0.303, well below all P8B.2 model-free baselines (0.500).
2. **ROC-AUC below 0.5 (0.257)** indicates poor out-of-sample ranking on the current chronological split — worse than random ordering for the positive class.
3. **Current P1 learned model is not acceptable for progression** to hyperparameter search, production backtest, or signal generation.

### P1 0.25 EM sensitivity (non-gate)

Target: `close_near_primary_pin_025` (0.25 EM band). Test balanced_acc 0.282, recall 0.0 — even weaker OOS. Confirms sensitivity track is informational only.

---

## 4. P2 Optional Review

### Naming clarification (documentation)

Label suffix `_025` in `close_above_below_primary_pin_025` and spec `p2_multinomial_025` refers to the **0.25 EM** threshold (same convention as P1 `_025`), **not** 0.025 EM.

Any human-readable label **"P2 0.025"** in informal notes is a **wording typo**; correct form is **"P2 @ 0.25 EM"**. Model/spec identifiers (`p2_multinomial_025`) are unchanged. Metrics artifacts are not modified in this stage.

### Results summary

| Spec | Target threshold | Train macro F1 | Test macro F1 | Test balanced_acc |
|------|------------------|----------------|---------------|-------------------|
| `p2_multinomial_050` | 0.50 EM | 0.994 | 0.335 | 0.307 |
| `p2_multinomial_025` | 0.25 EM | 1.000 | 0.540 | 0.475 |

P2 was optional and not gate-required. Both show train-near-perfect fit with substantial OOS drop for `_050`; `_025` test metrics are slightly better but still reflect regime shift (validation `near` class n=1 for `_025`).

P8B.2 did not define direct P2 model-free baselines; P2 remains diagnostic only.

---

## 5. Overfit / OOS Degradation Assessment

```text
Severity: HIGH for P0 Linear and P1 primary; MODERATE for P0 Ridge; MIXED for P2 optional.
Pattern: Strong in-sample fit + weak chronological OOS test (2025 sessions).
Learned models did not beat simple model-free references on primary gates (P0 test MAE, P1 test balanced_acc).
```

This is consistent with a **research-stage negative OOS baseline result** — valuable as a documented floor, not as a production candidate.

---

## 6. Likely Causes (Non-Exhaustive)

Listed as hypotheses, not proven root causes:

| Factor | Notes |
|--------|-------|
| 19 sessions vs 198 raw features | Very small session count; ~168 numeric features after filtering → high dimensionality relative to independent sessions |
| Feature/row ratio | ~810 train rows but features likely collinear; effective DOF still large vs 11 train sessions |
| Session regime shift | Test sessions (2025) chronologically after train (2024); market/volatility regime may differ |
| Chronological OOS harder than random split | By design per P8A protocol; correctly penalizes temporal leakage but exposes generalization gap |
| Target noise | P0 distance-in-EM is continuous with heavy tails (outlier_rate 0.51 on Ridge test) |
| P1 class imbalance | Train near ~25.7%; validation ~16.4%; model chases minority class in-sample |
| Zone-related feature sparsity | Frozen contract gates leave many zone features sparse (see governance sparse-zone note) |

---

## 7. What This Result Does NOT Mean

| Statement | Status |
|-----------|--------|
| Proves the market signal is impossible | **Does NOT** — only that this feature matrix + simple linear models failed OOS |
| Authorizes production use | **Does NOT** |
| Justifies hyperparameter search | **Does NOT** |
| Justifies test-set tuning | **Does NOT** |
| Invalidates P8B.0–P8B.2 harness work | **Does NOT** — harness and baselines remain valid reference |

This is a **research-stage negative OOS baseline result**. Model-free baselines (`zero_em`, majority/constant P1) remain the current best reference on test primary metrics.

---

## 8. Compliance (P8B.3.3 Stage)

| Check | Status |
|-------|--------|
| Model fitting in this stage | **NO** |
| `.fit()` called | **NO** |
| New feature build | **NO** |
| Artifacts committed | **NO** |
| `label_spec.md` modified | **NO** |
| `requirements.txt` modified | **NO** |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial P8B.3.3 result review |

---

**End of review.**
