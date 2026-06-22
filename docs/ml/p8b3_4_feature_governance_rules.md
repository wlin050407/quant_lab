# ML-P8B.3.4 Feature Governance Rules

**Date:** 2026-06-21  
**Stage:** ML-P8B.3.4  
**Plan:** [`p8b3_4_feature_reduction_stability_diagnostic_plan.md`](p8b3_4_feature_reduction_stability_diagnostic_plan.md)  
**Implementation gate:** [`p8b3_5_diagnostic_implementation_gate.md`](p8b3_5_diagnostic_implementation_gate.md)

---

## 1. Scope

Rules governing **feature reduction diagnostics** and **reduced feature set proposals** for the ML-P8B track. Applies to P8B.3.5 implementation and any future modeling that consumes reduced features.

Does **not** authorize model fitting, hyperparameter search, or production use.

---

## 2. Allowed Diagnostic Inputs

| Input | Purpose |
|-------|---------|
| P8B.1 validated feature dataset | `artifacts/features/pit_features_baseline_v1_1_validation/` |
| P7.8.3 / P8B.1 validated label dataset | Row alignment, join keys, `baseline_target_eligible` counts only |
| [`feature_catalog.md`](feature_catalog.md) | Group membership, naming, semantics |
| [`multiresolution_feature_spec.md`](multiresolution_feature_spec.md) | Resolution / early-window expectations |
| Source timestamps in feature rows | Freshness vs `as_of_timestamp` |
| Train / validation / test split metadata | Same configured 11/3/5 sessions as P8B.2/P8B.3.2 |
| P8B.1 feature manifest hash | Reproducibility |

---

## 3. Forbidden Diagnostic Inputs (Feature Selection)

Must **not** be used to include/exclude features:

```text
test metrics (MAE, balanced_accuracy, ROC-AUC, etc.)
validation metrics unless pre-declared as non-target data quality fail rule
future returns or post-as_of price paths
official_close
labels.* as feature columns
target columns (P0/P1/P2 label fields)
trading PnL
production backtest results
P8B.3.2 learned model coefficients or importances for selection
full-dataset target correlation (train+val+test)
```

---

## 4. Train-Only Feature Selection Rule

```text
1. All inclusion/exclusion decisions MUST be computable from train-split rows only.
2. train_sessions_used_for_selection MUST be recorded in manifest.
3. Correlation pruning MUST use train numeric matrix only.
4. Missingness thresholds MUST be evaluated on train only.
5. Constant/near-constant detection MUST use train only.
```

If a feature fails a **pre-declared non-target quality rule** on validation (e.g., 100% missing on validation), it may be **flagged** in the monitoring report but must **not** be auto-dropped based on validation unless that rule was written in P8B.3.4/3.5 docs before diagnostics run.

---

## 5. Validation / Test Monitoring Rule

| Split | Role |
|-------|------|
| Train | Selection + primary diagnostics |
| Validation | **Monitoring only** — distribution drift, missingness shift |
| Test | **Monitoring only** — same; never feeds selection |

Reports must label sections explicitly:

```text
selection_basis: train_only
validation_section: monitoring_only
test_section: monitoring_only
```

---

## 6. Feature Set Version Naming

Proposal version for first reduced set family:

```text
feature_set_version = p8b3_reduced_features_v0_proposal
```

Future versions increment when selection rules or thresholds change:

```text
p8b3_reduced_features_v0_proposal   — initial P8B.3.5 output (proposal)
p8b3_reduced_features_v1_<name>     — after owner approval of rule changes
```

Candidate set IDs (within a version):

```text
FeatureSet_A_core_stable
FeatureSet_B_core_plus_flow
FeatureSet_C_diagnostic_full_pruned
```

---

## 7. Reduced Feature Set Manifest Requirements

When P8B.3.5 generates a proposal manifest, it **must** include:

| Field | Required |
|-------|----------|
| `feature_set_version` | yes |
| `candidate_set_id` | yes (A / B / C) |
| `selection_rules` | yes (rule IDs + threshold values) |
| `selected_features` | yes (ordered list) |
| `excluded_features` | yes |
| `exclusion_reasons` | yes (map feature → reason code) |
| `train_sessions_used_for_selection` | yes |
| `validation_sessions_monitoring_only` | yes |
| `test_sessions_monitoring_only` | yes |
| `code_commit` | yes |
| `input_feature_manifest_hash` | yes |
| `created_at` | yes |
| `stage` | `ML-P8B.3.5` |
| `model_fitting_allowed` | **false** |
| `target_based_selection` | **false** |

Reason codes (minimum set):

```text
train_all_nan
train_missingness_exceeded
train_constant
train_near_constant
train_correlation_redundant
train_session_instability
group_rule_excluded
catalog_non_numeric_excluded
```

---

## 8. Correlation Prune Priority (Train-Only)

When \|r\| > `correlation_prune_threshold`, keep higher-priority feature:

| Priority | Group |
|----------|-------|
| 1 | `quality` |
| 2 | `context` |
| 3 | `deterministic` |
| 4 | `index_path` |
| 5 | `greeks_iv` |
| 6 | `quote_microstructure` |
| 7 | `trade_flow_proxy` |
| 8 | `chain_summary` |
| 9 | `multiresolution` |
| 10 | zone-dependent / sparse deterministic |

Within same group: keep lower train missingness; tie-break by catalog order.

---

## 9. Artifact Policy

```text
All diagnostic outputs under artifacts/reports/ — gitignored
No parquet/csv/jsonl committed to git
No credentials in manifests
Proposal manifests are local reference only until owner approves a frozen version for future fit
```

---

## 10. Reproducibility Requirements

P8B.3.5 implementation must:

```text
read feature paths from config (same roots as P8B.1)
pin split sessions in config (configured 11/3/5)
record code_commit and input_feature_manifest_hash
record diagnostic script version / stage constant
use deterministic sorting for feature lists and correlation pairs
no random seeds required (unsupervised stats only)
```

---

## 11. Explicit Non-Authorization

This governance document does **not** authorize:

```text
model fitting (.fit())
hyperparameter search (P8B.4)
production backtest (P8B.5)
trading signals (P8B.6)
new feature build or ingest
target-based feature selection
```

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial feature governance rules |

---

**End of rules.**
