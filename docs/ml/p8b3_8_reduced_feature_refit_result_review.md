# ML-P8B.3.8 Reduced Feature Refit Result Review

**Date:** 2026-06-22  
**Stage:** ML-P8B.3.8  
**Status:** PASS (documentation review only — no fitting)  
**Branch:** `research/zdte-fusion-model`  
**Prerequisite:** ML-P8B.3.7 PASS  

**Sources:**

- [`p8b3_7_reduced_feature_refit_report.md`](p8b3_7_reduced_feature_refit_report.md)
- [`p8b3_7_reduced_feature_refit_gate.md`](p8b3_7_reduced_feature_refit_gate.md)
- [`p8b3_6_reduced_feature_owner_review.md`](p8b3_6_reduced_feature_owner_review.md)
- [`p8b3_6_reduced_feature_approval_record.md`](p8b3_6_reduced_feature_approval_record.md)
- [`p8b3_2_train_only_fitting_report.md`](p8b3_2_train_only_fitting_report.md)
- [`p8b2_model_free_baseline_report.md`](p8b2_model_free_baseline_report.md)

**Decision record:** [`p8b3_8_next_gate_decision.md`](p8b3_8_next_gate_decision.md)  
**Next stage gate:** [`p8c_dataset_expansion_entry_gate.md`](p8c_dataset_expansion_entry_gate.md)

---

## Review Scope

本阶段仅审查 P8B.3.7 产出、记录风险判断、形成 owner next-gate decision。**未**训练模型、**未**调用 `.fit()`、**未**进入 P8B.4。

---

## 4.1 Protocol Recap

| Item | Value |
|------|-------|
| Input joined rows | 1391 |
| Baseline-eligible rows | 1390 |
| Raw feature columns | 198 |
| FeatureSet_A | 27 features (`FeatureSet_A_core_stable`) |
| FeatureSet_B | 82 features (`FeatureSet_B_core_plus_flow`) |
| FeatureSet_C | 92 features — **not fitted** |
| Split protocol | Configured chronological **11 / 3 / 5** sessions |
| Train sessions | 2024-01-05 … 2024-10-04 (11) |
| Validation sessions | 2024-11-01, 2024-11-29, 2024-12-06 (3) |
| Test sessions | 2025-01-03 … 2025-05-02 (5) |
| Total distinct sessions | **19** |
| Preprocessing | `SimpleImputer(median)` + `StandardScaler`, **train-only fit** |
| Models fitted | P0 LinearRegression, P0 Ridge(α=1.0), P1 Logistic(C=1.0, max_iter=1000, class_weight=None, threshold=0.5), P1@0.25 sensitivity, P2 optional multinomial |
| Fixed hyperparameters | No GridSearchCV; no alpha sweep; no class_weight sweep |
| Train-only fitting | **Confirmed** — manifest `trained_on_sessions_only=true` |
| Hyperparameter search | **None** |
| Validation/test tuning | **None** — `test_not_used_for_tuning=true` |
| Production backtest | **None** |
| Trading signal | **None** |
| Reduced manifest version | `p8b3_reduced_features_v0_proposal` |
| `target_based_selection_used` | false |

Evaluation artifacts (local, gitignored):  
`artifacts/reports/p8b3_reduced_feature_refit/p8b3_7_evaluation_report.json`  
`artifacts/reports/p8b3_reduced_feature_refit/p8b3_7_run_manifest.json`

---

## 4.2 FeatureSet_A Review

### Three-way comparison (test split, primary tracks)

#### P0 — `close_distance_to_primary_pin_em` (MAE, lower is better)

| Model / Baseline | Test MAE | Notes |
|------------------|----------|-------|
| P8B.2 `zero_em` | **2.01** | Best model-free on test MAE |
| **P8B.3.7 A Ridge** | **2.04** | Δ vs zero_em: **+0.035** (rough parity, not clear win) |
| P8B.2 `train_median_em` | 2.17 | A Ridge better (−0.13) |
| P8B.2 `train_mean_em` | 2.32 | A Ridge better (−0.26) |
| P8B.3.2 full-feature Ridge | 3.65 | A Ridge **−1.61** |
| P8B.3.2 full-feature Linear | 74.55 | A Linear **−72.5** |

Train / validation context (A Ridge): train MAE 1.11, validation MAE 2.16 — moderate generalization gap on P0, but test MAE near `zero_em`.

#### P1 @ 0.50 — `close_near_primary_pin_050` (balanced accuracy, higher is better)

| Model / Baseline | Test balanced_acc | Notes |
|------------------|-------------------|-------|
| **P8B.3.7 A Logistic** | **0.584** | Primary learned candidate |
| P8B.2 `majority_class` | 0.500 | A **+0.084** |
| P8B.2 `constant_not_near` | 0.500 | A **+0.084** |
| P8B.2 `train_prior_probability` | 0.500 | A **+0.084** |
| P8B.3.2 full-feature Logistic | 0.303 | A **+0.281** |

Train / validation context (A Logistic): train 0.913, validation 0.877 — strong in-sample; test 0.584 still above model-free but with expected degradation.

### Binding conclusions (FeatureSet_A)

1. **FeatureSet_A substantially improved over full-feature learned models** on both P0 and P1 test metrics.
2. **FeatureSet_A P1 @ 0.50 beat model-free majority on test balanced accuracy** (+0.084).
3. **FeatureSet_A P0 Ridge roughly matched `zero_em` but did not clearly beat it** (+0.035 MAE on test).
4. **FeatureSet_A is the current best learned candidate**, but only as a **research-stage provisional result** — evidence base is 19 sessions and one pre-declared chronological split.

---

## 4.3 FeatureSet_B Review

### Test split (primary tracks)

| Track | FeatureSet_B | FeatureSet_A | P8B.2 baseline |
|-------|--------------|--------------|----------------|
| P0 Ridge MAE | **3.37** | 2.04 | zero_em 2.01 |
| P1 @0.50 balanced_acc | **0.410** | 0.584 | majority 0.500 |

### Binding conclusions (FeatureSet_B)

1. **FeatureSet_B did not improve over FeatureSet_A** on either primary track.
2. **FeatureSet_B P0 Ridge was worse than A and `zero_em`** (3.37 vs 2.04 / 2.01).
3. **FeatureSet_B P1 @ 0.50 was worse than A and majority baseline** (0.410 vs 0.584 / 0.500).
4. **FeatureSet_B should not be promoted to default.** It remains **sensitivity-only** per P8B.3.6 approval.

P2 optional metrics on B (e.g. P2@0.25 test balanced_acc 0.698) do **not** override primary-track failure vs A and do not justify default promotion.

---

## 4.4 Full-Feature Comparison (P8B.3.2 → P8B.3.7)

| Issue (P8B.3.2 full-feature) | P8B.3.7 reduced-feature (A) | Interpretation |
|------------------------------|----------------------------|----------------|
| P0 Linear test MAE 74.55 | P0 Linear test MAE 2.06 | Catastrophic OOS collapse mitigated |
| P0 Ridge test MAE 3.65 | P0 Ridge test MAE 2.04 | Large improvement; near model-free |
| P1 test balanced_acc 0.303 | P1 test balanced_acc 0.584 | Restored above model-free majority |
| 168 numeric features, 11 train sessions | 27 features | Feature governance reduced overfit risk |

**Conclusion:**

- **Reduced features mitigated the OOS degradation seen in P8B.3.2.**
- **The result supports feature governance, not hyperparameter search.** The fix was column selection under train-only unsupervised rules (P8B.3.5), not tuning Ridge α or Logistic C.

---

## 4.5 What This Result Does NOT Authorize

| Claim | Status |
|-------|--------|
| P8B.4 hyperparameter search | **NOT authorized** |
| Production backtest (P8B.5) | **NOT authorized** |
| Trading signal generation (P8B.6) | **NOT authorized** |
| Generalization across broader regimes | **NOT proven** — 19 sessions, single split |
| Tuning to the current test split | **NOT justified** — test was monitoring only |
| FeatureSet_B as default | **NOT approved** |
| FeatureSet_C refit | **NOT approved** |
| Committing evaluation artifacts | **NOT done** |

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Small sample (19 sessions) | High | ML-P8C controlled dataset expansion before reconsidering P8B.4 |
| Single chronological split | High | Pre-declare expansion dates; preserve no-leak gates |
| P0 learned ≈ `zero_em` | Medium | Do not claim P0 learned alpha; keep model-free P0 as benchmark |
| P1 train/val >> test | Medium | Expanded OOS validation required before production path |
| Regime concentration (2024–2025) | Medium | Define regime coverage targets in P8C |

---

## P8B.3.8 PASS Attestation

```text
[x] FeatureSet_A result reviewed
[x] FeatureSet_B result reviewed
[x] Comparison vs P8B.2 documented
[x] Comparison vs P8B.3.2 documented
[x] FeatureSet_A accepted as provisional candidate (see next_gate_decision)
[x] FeatureSet_B remains sensitivity-only
[x] P8B.4 / P8B.5 / P8B.6 remain blocked
[x] P8C entry gate written
[x] No model fitting in this stage
[x] No .fit() in this stage
[x] label_spec.md unchanged
[x] requirements.txt unchanged
```

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial P8B.3.8 result review (PASS) |
