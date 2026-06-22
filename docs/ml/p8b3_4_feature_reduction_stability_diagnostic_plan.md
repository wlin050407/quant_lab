# ML-P8B.3.4 Feature Reduction and Stability Diagnostic Plan

**Date:** 2026-06-21  
**Branch:** `research/zdte-fusion-model`  
**Stage:** ML-P8B.3.4  
**Gate:** **PASS** (planning only — no diagnostics executed, no fitting)

**Prior decisions:**

- [`p8b3_3_learned_baseline_result_review.md`](p8b3_3_learned_baseline_result_review.md)
- [`p8b3_next_gate_decision.md`](p8b3_next_gate_decision.md)
- [`p8b3_2_train_only_fitting_report.md`](p8b3_2_train_only_fitting_report.md)
- [`p8b2_model_free_baseline_report.md`](p8b2_model_free_baseline_report.md)
- [`p8b1_feature_dataset_validation_report.md`](p8b1_feature_dataset_validation_report.md)

**Companion docs:**

- [`p8b3_4_feature_governance_rules.md`](p8b3_4_feature_governance_rules.md)
- [`p8b3_5_diagnostic_implementation_gate.md`](p8b3_5_diagnostic_implementation_gate.md)

---

## 1. Current Problem Statement

### P8B.3.2 / P8B.3.3 findings

```text
P8B.3.2 learned baseline showed negative OOS result.
P0: zero_em (test MAE 2.01 EM) remains best test reference.
     Ridge test MAE 3.65; Linear test MAE 74.55 — both worse than zero_em.
P1: model-free majority / constant / train_prior (test balanced_acc 0.500)
     beat learned LogisticRegression (test balanced_acc 0.303, ROC-AUC 0.257).
The next step is NOT hyperparameter search.
```

### Structural mismatch

| Dimension | Current state |
|-----------|---------------|
| Sessions | 19 |
| Raw feature columns (P8B.1) | 198 |
| Numeric columns used in P8B.3.2 | 168 (after type filter) |
| Train sessions | 11 |
| Train rows (baseline-eligible) | ~810 |
| Effective ratio | ~198 features vs 19 independent sessions — high risk of spurious fit |

Additional factors from P8B.1 / P8B.3.3:

```text
feature/row regime mismatch
possible sparse / unstable / redundant feature groups
chronological OOS regime shift (2024 train → 2025 test)
zone-dependent features high missingness (~94% for distance_spot_to_zone_*)
12 train all-NaN columns dropped only at P8B.3.2 fit time (not pre-governed)
```

### Gate status (unchanged)

```text
P8B.4 hyperparameter search: BLOCKED
P8B.5 production backtest: BLOCKED
P8B.6 trading signal generation: BLOCKED
Feature diagnostics are required before any further learned fitting.
```

**P8B.3.4 does not execute diagnostics.** It defines the protocol for **ML-P8B.3.5**.

---

## 2. Purpose

Design a **governed, train-only, unsupervised** feature reduction and stability diagnostic program that:

1. Characterizes missingness, sparsity, redundancy, and drift in the existing P8B.1 feature matrix.
2. Proposes **versioned reduced feature sets** without using target performance for selection.
3. Establishes preconditions for any future learned re-fit (still not P8B.4).
4. Does **not** imply that reduced features will beat `zero_em` or model-free P1 baselines.

---

## 3. Input Artifacts (Future P8B.3.5)

| Artifact | Path | Use |
|----------|------|-----|
| P8B.1 features | `artifacts/features/pit_features_baseline_v1_1_validation/` | Primary diagnostic input |
| P8B.1 labels (alignment only) | `artifacts/datasets/pit_sample_baseline_v1_1_validation/` | Row keys, eligibility counts — **not** target correlation for selection |
| P8B.2 split config | `config/ml/p8b2_model_free_baselines.yaml` / P8B.3 config split block | Session-grouped train/val/test |
| Feature catalog | [`feature_catalog.md`](feature_catalog.md) | Group membership, semantics |
| Multiresolution spec | [`multiresolution_feature_spec.md`](multiresolution_feature_spec.md) | Early-window missingness expectations |

No new ingest. No new feature build in P8B.3.4 or P8B.3.5.

---

## 4. Diagnostic Dimensions (P8B.3.5 — Not Executed in P8B.3.4)

Future implementation must compute **read-only** statistics. No `.fit()`. No model training.

### 4.1 Missingness

| Diagnostic | Description | Split scope |
|------------|-------------|-------------|
| `missingness_by_feature` | Per-column null rate | train / val / test reported separately |
| `missingness_by_feature_group` | Aggregate by catalog group (`context`, `deterministic`, …) | train primary; val/test monitor |
| `missingness_by_split` | Overall matrix sparsity per split | all splits |
| `multiresolution_early_window_missingness` | `mr_*`, short quote/index windows at session open | train + by-session |
| `zone_dependent_sparse_features` | `distance_spot_to_zone_*`, zone width, spot_position_in_zone | train + by-session |

### 4.2 Constant / degenerate features

| Diagnostic | Description |
|------------|-------------|
| `constant_feature_detection` | Zero variance on train |
| `near_constant_detection` | ≥99% same value on train (proposal threshold) |
| `nan_inf_counts` | Cell-level NaN / inf tallies per feature per split |
| `train_all_nan_features` | Columns with 100% missing on train (already 12 in P8B.3.2) |

### 4.3 Distribution drift (monitoring, not selection)

| Diagnostic | Description | Selection use |
|------------|-------------|-----------------|
| `feature_value_distribution_by_split` | Mean/std/quantiles per numeric feature | **Monitor only** |
| `feature_value_distribution_by_session` | Per-session summary for stability | **Monitor only** |
| `feature_group_stability_by_session` | Group-level missingness variance across train sessions | Train-only stability ranking |

### 4.4 Redundancy (train-only)

| Diagnostic | Description |
|------------|-------------|
| `pairwise_correlation_clusters` | Spearman/Pearson on train numeric matrix |
| `high_correlation_pairs` | \|r\| > 0.95 proposal threshold |
| `duplicate_feature_candidates` | Identical or near-identical train columns |

### 4.5 Timestamp / quality

| Diagnostic | Description |
|------------|-------------|
| `source_timestamp_freshness` | `as_of - source_timestamp_max` margin |
| `quality_feature_summary` | `feature_quality_score`, stale ratios |
| `high_sparsity_features` | Train missingness > 80% proposal threshold |

### Mandatory constraints

```text
Diagnostics must not use test performance for feature selection.
Diagnostics must not fit models.
Diagnostics must not call .fit().
Validation/test outputs are monitoring reports only unless pre-declared as non-target data quality fail rules.
```

---

## 5. Train-Only Selection Rule

Any **reduced feature set** intended for future modeling must be selected using:

1. **Pre-declared feature group rules** (catalog groups, explicit allow/deny lists), and/or  
2. **Train-session-only unsupervised diagnostics** (missingness, constant, correlation pruning).

### Forbidden selection criteria

```text
selecting features because they improve validation score
selecting features because they improve test score
selecting features based on full-dataset target correlation
selecting features after seeing P8B.3.2 test failures and tuning to that test split
using labels.* columns as inputs
using official_close or future_* fields
```

### Allowed

```text
report validation/test diagnostics separately for monitoring
use validation/test only for pre-declared non-target data quality fail rules
  (e.g., "feature X has 100% missing on validation" → flag, not "drop because val AUC improved")
```

Selection manifest must record **train_sessions_used_for_selection** only.

---

## 6. Candidate Feature Reduction Principles

Applied **train-only** when P8B.3.5 generates proposals:

| Rule | Action |
|------|--------|
| Train missingness above threshold | Exclude; reason = `train_missingness_exceeded` |
| Train all-NaN | Exclude; reason = `train_all_nan` |
| Constant / near-constant on train | Exclude; reason = `train_constant` / `train_near_constant` |
| \|correlation\| > threshold with kept feature | Exclude lower-priority member; reason = `train_correlation_redundant` |
| Unstable high missingness across train sessions | Flag or exclude; reason = `train_session_instability` |
| Priority order | `quality` → `context` → `deterministic` → `index_path` → flow/greeks → sparse zone |

**Prefer:**

- Stable, low-missingness features
- Deterministic / context / quality before sparse zone-dependent features
- Interpretable feature groups
- Documented exclusion reason for every dropped column

### Proposal thresholds (diagnostic only)

```text
train_missingness_drop_threshold = 80%
near_constant_threshold = 99% same value on train
correlation_prune_threshold = 0.95 absolute Pearson on train (after imputation for correlation matrix only — no model fit)
```

```text
Thresholds are diagnostic proposal only.
They do not authorize model fitting.
They do not authorize hyperparameter search.
Owner may adjust thresholds in P8B.3.5 manifest with documented rationale.
```

---

## 7. Candidate Reduced Feature Sets (Definitions Only)

These are **future candidate definitions**. No matrices generated in P8B.3.4. No model fitting authorized.

### FeatureSet_A_core_stable

```text
Name: FeatureSet_A_core_stable
Intent: Minimal stable interpretable core

Includes (subject to train missingness filter):
  - context (session clock, session metadata numerics)
  - deterministic (pin/spot/EM distances where non-null; exclude raw zone string fields)
  - quality (feature_quality_score, stale ratios, replay flags)
  - selected index_path (low-missingness index returns/vol, not full 35 if sparse)

Excludes:
  - high-missingness zone-dependent features (distance_spot_to_zone_*, zone_width_*, spot_position_in_zone)
  - multiresolution features with >80% train missingness
  - chain_summary features with >80% train missingness unless stability review passes

Target size (proposal): ~40–60 numeric features after pruning
```

### FeatureSet_B_core_plus_flow

```text
Name: FeatureSet_B_core_plus_flow
Intent: Core + liquid microstructure proxies

Includes:
  - all FeatureSet_A_core_stable survivors
  - selected quote_microstructure (30s/60s windows; exclude duplicate-heavy early session if unstable)
  - selected trade_flow_proxy (300s / since_open aggregates with acceptable train missingness)
  - selected greeks_iv (IV ATM, gamma-OI summaries)
  - train-only missingness and correlation filtered

Excludes:
  - redundant quote/trade pairs (correlation prune)
  - features failing train stability across sessions

Target size (proposal): ~80–120 numeric features after pruning
```

### FeatureSet_C_diagnostic_full_pruned

```text
Name: FeatureSet_C_diagnostic_full_pruned
Intent: Maximum catalog coverage with unsupervised pruning

Includes:
  - all catalog groups allowed in P8B.1 matrix
  - train-only missingness / constant / correlation pruning
  - zone sparse features kept ONLY if train missingness ≤ 80% AND session stability pass

Excludes:
  - train all-NaN, constant, near-constant
  - one member per high-correlation cluster (priority table in governance rules)

Target size (proposal): ~100–140 numeric features (vs 168 ungoverned P8B.3.2)
```

```text
These are future candidate definitions only.
No model fitting is authorized in P8B.3.4.
P8B.3.5 may emit proposal manifests; learned re-fit requires separate gate after P8B.3.5 PASS + owner review.
```

---

## 8. Label / Target Usage Rule

```text
Default: no target-based feature selection.
Target columns may be loaded only to confirm row alignment and eligibility counts
  (baseline_target_eligible, join key validation).
Any train-only target correlation analysis (e.g., univariate association with P0/P1)
  requires separate owner approval — not in default P8B.3.5 scope.
```

Forbidden as diagnostic inputs for selection:

```text
labels.close_*
labels.* as feature columns
official_close
normalized_close_move
any metric derived from post-as_of outcomes
```

---

## 9. Outputs (Future P8B.3.5)

Planned artifacts (local, gitignored):

```text
artifacts/reports/p8b3_4_feature_diagnostics/
  p8b3_5_missingness_report.json
  p8b3_5_stability_report.json
  p8b3_5_correlation_report.json
  p8b3_5_reduced_feature_set_proposal.json
  p8b3_5_run_manifest.json
```

---

## 10. Relationship to Other Stages

| Stage | Relationship |
|-------|--------------|
| P8B.3.5 | Implements this plan (diagnostics only) |
| P8B.3.x re-fit | Blocked until P8B.3.5 PASS + governance review |
| P8B.4 | Blocked until feature diagnostics + owner approval |
| P8C dataset expansion | Recommended **after** P8B.3.5; see [`p8b3_next_gate_decision.md`](p8b3_next_gate_decision.md) |

---

## 11. P8B.3.4 Compliance

| Check | Status |
|-------|--------|
| Diagnostics executed | **NO** |
| Model fitting / `.fit()` | **NO** |
| New feature build | **NO** |
| Artifacts committed | **NO** |
| `label_spec.md` modified | **NO** |
| `requirements.txt` modified | **NO** |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial P8B.3.4 diagnostic plan |

---

**End of plan.**
