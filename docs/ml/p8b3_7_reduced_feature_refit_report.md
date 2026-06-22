# ML-P8B.3.7 Reduced-Feature Train-Only Learned Refit Report

**Stage:** ML-P8B.3.7  
**Status:** PASS  
**Date:** 2026-06-22  
**Branch:** `research/zdte-fusion-model`  
**Pre-commit hash:** `d201445c5daa1bf4895da5151a6a8244bd279ae9`

---

## Executive Summary

P8B.3.7 在固定超参与 11/3/5 session split 下，对 **FeatureSet_A_core_stable**（27 features）与 **FeatureSet_B_core_plus_flow**（82 features）完成 train-only refit，并与 P8B.2 model-free 及 P8B.3.2 全特征 learned baseline 对比。

**核心结论：**

1. **FeatureSet A 显著降低 OOS 退化**：相对 P8B.3.2 全特征模型，P0 test MAE 从 ~3.65 降至 ~2.04；P1 test balanced accuracy 从 ~0.30 升至 ~0.58。
2. **FeatureSet A 在 P1 test 上优于 P8B.2 majority baseline**（0.584 vs 0.500）；P0 test MAE 与 `zero_em`（2.01）基本持平（Ridge 2.04，delta +0.035）。
3. **FeatureSet B 未优于 A**：test 上 P0/P1 均弱于 A；按 P8B.3.6 规则，**不得自动将 B 设为默认**。
4. **FeatureSet_C 未拟合**；无 hyperparameter search；无 validation/test tuning；无 backtest / trading signal。
5. **P8B.4 仍 BLOCKED**。下一步：**ML-P8B.3.8 — Reduced Feature Refit Result Review**。

---

## Compliance Attestation

- Model fitting was performed **only on training sessions**.
- No hyperparameter search was performed.
- No validation/test tuning was performed.
- No production backtest was performed.
- No trading signal was generated.
- **P8B.4 remains blocked.**
- `docs/ml/label_spec.md` **unchanged**.
- `requirements.txt` **unchanged**.
- Artifacts **not committed** (`artifacts/reports/p8b3_reduced_feature_refit/` gitignored).

---

## Input Summary

| Item | Value |
|------|-------|
| Features | `artifacts/features/pit_features_baseline_v1_1_validation/` |
| Labels | `artifacts/datasets/pit_sample_baseline_v1_1_validation/` |
| Joined rows | 1391 |
| Baseline-eligible | 1390 |
| Raw feature columns | 198 |
| Reduced manifest | `artifacts/reports/p8b3_feature_stability_diagnostics/reduced_feature_set_manifest.json` |
| Manifest hash | `ad14a9004ecaa543` |
| `feature_set_version` | `p8b3_reduced_features_v0_proposal` |
| `target_based_selection_used` | false |
| `model_fitting_performed` (manifest) | false |

---

## Reduced Feature Manifest Summary

| Set | Features | P8B.3.7 role | Fitted |
|-----|----------|--------------|--------|
| FeatureSet_A_core_stable | 27 | Primary | Yes |
| FeatureSet_B_core_plus_flow | 82 | Sensitivity | Yes |
| FeatureSet_C_diagnostic_full_pruned | 92 | Forbidden | No |

FeatureSet A groups: context, deterministic, index_path, quality.  
FeatureSet B adds: quote_microstructure, trade_flow_proxy, greeks_iv.

---

## Split Protocol

| Split | Sessions | Count |
|-------|----------|-------|
| Train | 2024-01-05 … 2024-10-04 | 11 |
| Validation | 2024-11-01, 2024-11-29, 2024-12-06 | 3 |
| Test | 2025-01-03 … 2025-05-02 | 5 |

**Split validation:** PASS  
**Row-level random split:** none detected  
**Forbidden input:** PASS  
**P1 0.50 dual-class (train + validation):** PASS  

---

## Preprocessing

| Step | Policy |
|------|--------|
| Imputer | `SimpleImputer(strategy="median")`, fit on **train only** |
| Scaler | `StandardScaler`, fit on **train only** |
| Transform | validation / test transform only |
| Feature columns | Frozen per feature set from manifest (train numeric filter) |

---

## Fixed Hyperparameters

| Model | Parameters |
|-------|------------|
| LinearRegression | default |
| Ridge | alpha = 1.0 |
| LogisticRegression (P1/P2) | C = 1.0, max_iter = 1000, class_weight = None |
| P1 threshold | 0.5 (fixed) |
| P2 | solver = lbfgs (sklearn 1.9 compatible) |

No GridSearchCV / multiple alpha / class_weight sweep.

---

## FeatureSet_A Results

### P0 — `close_distance_to_primary_pin_em`

| Model | Train MAE | Val MAE | **Test MAE** |
|-------|-----------|---------|--------------|
| LinearRegression | 1.11 | 2.19 | **2.06** |
| Ridge | 1.11 | 2.16 | **2.04** |

**Test comparison vs P8B.2 (MAE, lower is better):**

| Baseline | Test MAE | Ridge delta |
|----------|----------|-------------|
| zero_em | 2.01 | +0.035 (Ridge slightly worse) |
| train_median_em | 2.17 | −0.13 (Ridge better) |
| train_mean_em | 2.32 | −0.26 (Ridge better) |

**Test comparison vs P8B.3.2 full-feature:**

| Full-feature spec | Full test MAE | A Ridge test MAE | Delta |
|-------------------|---------------|------------------|-------|
| p0_ridge_regression | 3.65 | 2.04 | **−1.61** |
| p0_linear_regression | 74.55 | 2.06 | **−72.5** |

### P1 @ 0.50 — `close_near_primary_pin_050`

| Split | Balanced Acc | Precision | Recall | F1 | Brier | ROC-AUC |
|-------|--------------|-----------|--------|-----|-------|---------|
| Train | 0.913 | — | — | — | — | — |
| Validation | 0.877 | — | — | — | — | — |
| **Test** | **0.584** | — | — | — | — | — |

**Test comparison vs P8B.2 (balanced accuracy, higher is better):**

| Baseline | Test | A Logistic delta |
|----------|------|------------------|
| majority_class | 0.500 | **+0.084** |
| constant_not_near | 0.500 | **+0.084** |
| train_prior_probability | 0.500 | **+0.084** |

**Test comparison vs P8B.3.2 full-feature Logistic:** 0.584 vs 0.303 (**+0.281**).

### P1 @ 0.25 (sensitivity)

Test balanced accuracy: **0.583** (marked sensitivity only).

### P2 (optional)

Both P2 multinomial specs **fitted** (train classes sufficient). Test balanced accuracy: P2@0.50 **0.623**, P2@0.25 **0.567**.

---

## FeatureSet_B Results

### P0 — test MAE

| Model | Test MAE |
|-------|----------|
| LinearRegression | 3.12 |
| Ridge | **3.37** |

Worse than FeatureSet A and `zero_em` (2.01). Better than full-feature Ridge (3.65) but not better than A.

### P1 @ 0.50 — test

Balanced accuracy: **0.410** — below majority (0.500) and well below A (0.584).

### P1 @ 0.25 (sensitivity)

Test balanced accuracy: **0.378**.

### P2 (optional)

Fitted. Test balanced accuracy: P2@0.50 **0.407**, P2@0.25 **0.698** (P2@0.25 test metric higher but P1 primary track fails vs A).

---

## Interpretation (P8B.3.6 Binding Rules)

| Rule | Application |
|------|-------------|
| A fails zero_em / majority on test → block learned modeling | **Partial pass:** A **beats majority** on P1 test; P0 Ridge test MAE **≈ zero_em** (+0.035, not a clear win). Learned modeling **not fully validated** for P0; P1 shows signal. |
| A improves validation but fails test → instability | A validation metrics strong; test P1 **improves** vs baselines — not pure val-only overfit pattern for P1. P0 test ~ baseline. |
| A improves test but B fails → prefer A | **Yes.** B test P0/P1 both worse than A. **Prefer A**; do not expand to B by default. |
| B improves over A → owner review before default | B **does not** improve over A on primary tracks. No owner escalation for B-as-default. |
| No P8B.4 from P8B.3.7 alone | **Confirmed.** P8B.4 remains blocked. |

**Does reduced feature set A/B reduce OOS degradation under fixed protocol?**

- **A: Yes**, vs P8B.3.2 full-feature (large test metric improvement).
- **B: Mixed** — vs full-feature yes for P0; vs A **no** on primary P0/P1 test.

---

## Run Manifest Summary

Path: `artifacts/reports/p8b3_reduced_feature_refit/p8b3_7_run_manifest.json`

| Field | Value |
|-------|-------|
| stage | ML-P8B.3.7 |
| model_fitting_allowed | true |
| feature_sets_used | FeatureSet_A_core_stable, FeatureSet_B_core_plus_flow |
| feature_set_version | p8b3_reduced_features_v0_proposal |
| preprocessing_fit_on_train_only | true |
| test_not_used_for_tuning | true |
| hyperparameter_search_performed | false |
| p8b4_blocked | true |
| dataset_manifest_hash | 1818cdd2d90433a6 |
| feature_manifest_hash | 0b01c15c7380bb5c |
| reduced_feature_manifest_hash | ad14a9004ecaa543 |

Evaluation report: `artifacts/reports/p8b3_reduced_feature_refit/p8b3_7_evaluation_report.json`

---

## Execution Log

### Dry-run

```bash
python scripts/run_reduced_feature_refit.py \
  --config config/ml/p8b3_reduced_feature_refit.yaml \
  --dry-run \
  --feature-set A,B
```

**Result:** PASS (`p8b3_7_pass: true`)

### Execute

```bash
python scripts/run_reduced_feature_refit.py \
  --config config/ml/p8b3_reduced_feature_refit.yaml \
  --execute \
  --feature-set A,B
```

**Result:** PASS (`p8b3_7_pass: true`)

---

## Tests & Lint

```bash
python -m pytest -q tests/test_p8b3_reduced_feature_refit.py          # 16 passed
python -m pytest -q tests/test_p8b3_train_only_fitting.py            # passed
python -m pytest -q tests/test_p8b3_feature_stability_diagnostics.py # passed
python -m ruff check src/quant_lab/ml/harness/p8b3_fit.py \
  src/quant_lab/ml/harness/p8b3_7_refit.py \
  scripts/run_reduced_feature_refit.py \
  tests/test_p8b3_reduced_feature_refit.py                             # passed
```

---

## Modified Files (This Stage)

| File | Change |
|------|--------|
| `config/ml/p8b3_reduced_feature_refit.yaml` | New P8B.3.7 config |
| `scripts/run_reduced_feature_refit.py` | New CLI |
| `src/quant_lab/ml/harness/p8b3_7_refit.py` | Reduced-feature refit orchestration |
| `src/quant_lab/ml/harness/p8b3_fit.py` | Add `comparison_vs_p8b3_2` field |
| `src/quant_lab/ml/harness/manifests.py` | Add `HARNESS_STAGE_P8B3_7` |
| `tests/test_p8b3_reduced_feature_refit.py` | New tests |
| `docs/ml/p8b3_7_reduced_feature_refit_report.md` | This report |
| `docs/ml/p8b_staged_execution_plan.md` | P8B.3.7 PASS → P8B.3.8 |
| `docs/ml/label_target_governance_decision.md` | P8B.3.7 PASS |
| `docs/ml/p8b3_7_reduced_feature_refit_gate.md` | Status update |

---

## Next Gate Recommendation

**ML-P8B.3.8 — Reduced Feature Refit Result Review**

Owner should review:

1. Whether FeatureSet A P1 test lift (+0.084 vs majority) is sufficient to continue learned modeling path.
2. P0 test MAE parity with `zero_em` — whether P0 learned track adds value.
3. Confirm B remains sensitivity-only; do not authorize B as default without separate review.
4. **Do not authorize P8B.4** from this stage alone.

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial P8B.3.7 refit report (PASS) |
