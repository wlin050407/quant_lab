# ML-P8B.3.5 Feature Stability Diagnostics Report

**Date:** 2026-06-21  
**Branch:** `research/zdte-fusion-model`  
**Stage:** ML-P8B.3.5  
**Gate:** **PASS**

**Plan:** [`p8b3_4_feature_reduction_stability_diagnostic_plan.md`](p8b3_4_feature_reduction_stability_diagnostic_plan.md)  
**Governance:** [`p8b3_4_feature_governance_rules.md`](p8b3_4_feature_governance_rules.md)

---

## Summary

Implemented **train-only unsupervised** feature stability diagnostics on the existing P8B.1 feature matrix. Generated reduced feature set **proposals** (A/B/C). No model fitting, no `.fit()`, no target-based selection.

**Attestation:**

- No model fitting was performed.
- No sklearn `.fit()` was called.
- No target-based feature selection was performed.
- No validation/test performance was used for feature selection.
- No trading signal was generated.

---

## Input Summary

| Field | Value |
|-------|-------|
| Features | `artifacts/features/pit_features_baseline_v1_1_validation/` |
| Labels | `artifacts/datasets/pit_sample_baseline_v1_1_validation/` (alignment + eligibility only) |
| Joined rows | 1391 |
| Baseline-eligible rows | 1390 |
| Raw feature columns | 198 |
| Numeric feature columns | 180 |
| Non-numeric excluded | 18 |
| Sessions | 19 |
| Split | chronological configured 11 / 3 / 5 |

Labels used **only** for row join and `baseline_target_eligible` counts — not for feature selection.

---

## Split Summary

| Split | Sessions | Role |
|-------|----------|------|
| Train (11) | 2024-01-05 … 2024-10-04 | **Selection basis** |
| Validation (3) | 2024-11-01, 2024-11-29, 2024-12-06 | Monitoring only |
| Test (5) | 2025-01-03 … 2025-05-02 | Monitoring only |

Split validation: **PASS**  
Forbidden input validation: **PASS**

---

## Diagnostics Executed

| Dimension | Status |
|-----------|--------|
| missingness_by_feature | ✓ train / val / test |
| missingness_by_feature_group | ✓ |
| missingness_by_split | ✓ |
| missingness_by_session (train) | ✓ |
| constant / near-constant (train) | ✓ |
| NaN / inf summary | ✓ per split |
| correlation clusters (train) | ✓ |
| split / session drift monitoring | ✓ monitoring only |
| timestamp freshness | ✓ (available from row metadata) |

---

## Missingness Summary

**Train mean missingness by group (highest):**

| Group | Train mean missingness |
|-------|----------------------|
| multiresolution | 0.20 |
| chain_summary | 0.00 |
| context | 0.00 |
| deterministic | 0.00 |
| greeks_iv | 0.00 |

P8B.1 already noted high missingness on zone-distance and early-window index/multiresolution features; diagnostics confirm multiresolution as the highest group-level train missingness.

---

## Constant / Near-Constant Summary (Train)

| Flag | Feature count (of 180 numeric) |
|------|--------------------------------|
| all_nan_train | 4 |
| constant_train | 22 |
| near_constant_train (≥99% same value) | 22 |

These are excluded from proposals via `train_all_nan`, `train_constant`, `train_near_constant` reason codes.

---

## NaN / Inf Summary

Cell-level NaN/inf counts reported per split in `p8b3_5_feature_diagnostics.json` under `nan_inf_summary`. Inf values in raw features are coerced to NaN for numeric analysis (consistent with P8B.3.2 preprocessing policy).

---

## Correlation Cluster Summary (Train Only)

| Metric | Value |
|--------|-------|
| Threshold | \|r\| ≥ 0.95 |
| High-correlation pairs | 225 |
| Correlation clusters | 23 |

Pruning keeps higher-priority group member per cluster (quality → context → deterministic → …).

---

## Split / Session Stability Monitoring

- Per-feature mean/std/median and train-normalized mean shift reported for validation and test (**monitoring only**).
- Train session-level missingness variance flags unstable features (`unstable_train_features` in diagnostics JSON).
- **Not used** for feature inclusion/exclusion.

---

## Timestamp Freshness

Row-level `as_of_timestamp` and `source_timestamp_max` available. Summary statistics written to diagnostics JSON (`timestamp_freshness.status = available`). Leakage validation: **PASS**.

---

## Candidate Reduced Feature Sets

| Set | Selected | Excluded | Intent |
|-----|----------|----------|--------|
| **FeatureSet_A_core_stable** | **27** | 153 | context + deterministic + quality + index (no zone-sparse) |
| **FeatureSet_B_core_plus_flow** | **82** | 98 | A + quote/trade/greeks (train-pruned) |
| **FeatureSet_C_diagnostic_full_pruned** | **92** | 88 | all groups + full unsupervised prune |

Version: `p8b3_reduced_features_v0_proposal`

Thresholds applied (proposal only):

```text
train_missingness_drop_threshold = 0.80
near_constant_same_value_threshold = 0.99
correlation_prune_threshold = 0.95
```

---

## Manifest Outputs (Local, Not Committed)

| Artifact | Path |
|----------|------|
| Diagnostics | `artifacts/reports/p8b3_feature_stability_diagnostics/p8b3_5_feature_diagnostics.json` |
| Proposal manifest | `artifacts/reports/p8b3_feature_stability_diagnostics/reduced_feature_set_manifest.json` |
| Run manifest | `artifacts/reports/p8b3_feature_stability_diagnostics/p8b3_5_run_manifest.json` |

Key manifest fields:

```text
target_based_selection_used = false
model_fitting_performed = false
selection_scope = train_only_unsupervised
```

---

## CLI Results

```bash
python scripts/run_feature_stability_diagnostics.py \
  --config config/ml/p8b3_feature_stability_diagnostics.yaml --dry-run
# exit 0

python scripts/run_feature_stability_diagnostics.py \
  --config config/ml/p8b3_feature_stability_diagnostics.yaml
# exit 0
```

---

## Governance Compliance

| Check | Status |
|-------|--------|
| Train-only selection | PASS |
| Val/test monitoring only | PASS |
| No target-based selection | PASS |
| No `.fit()` | PASS |
| No hyperparameter search | PASS |
| Artifacts not committed | PASS |
| `label_spec.md` unchanged | PASS |
| `requirements.txt` unchanged | PASS |

---

## Why P8B.4 Remains Blocked

Reduced proposals shrink the feature space (27–92 vs 180 numeric) but **do not demonstrate OOS improvement**. P8B.3.3 negative learned baseline stands. Hyperparameter search would add tuning risk without governed feature set owner approval.

```text
P8B.4  hyperparameter search     BLOCKED
P8B.5  production backtest       BLOCKED
P8B.6  trading signal             BLOCKED
```

---

## Next Stage Recommendation

```text
ML-P8B.3.6 — Reduced Feature Set Owner Review
```

Owner selects A/B/C (or requests rule/threshold revision) before any optional train-only re-fit with reduced features.

---

## Implemented Code

| Path | Purpose |
|------|---------|
| `config/ml/p8b3_feature_stability_diagnostics.yaml` | Diagnostics config |
| `src/quant_lab/ml/harness/feature_diagnostics.py` | Diagnostic computations + orchestration |
| `src/quant_lab/ml/harness/p8b3_feature_selection.py` | FeatureSet A/B/C proposals |
| `scripts/run_feature_stability_diagnostics.py` | CLI |
| `tests/test_p8b3_feature_stability_diagnostics.py` | Unit tests |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial P8B.3.5 diagnostics report |

---

**End of report.**
