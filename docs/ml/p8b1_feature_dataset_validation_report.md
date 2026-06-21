# ML-P8B.1 — Feature Dataset Build and Leakage Validation Report

**Phase:** ML-P8B.1 — Feature Dataset Build and Leakage Validation  
**Branch:** `research/zdte-fusion-model`  
**Prior phase:** ML-P8B.0 — Modeling Harness Implementation  
**Config:** `config/ml/pit_features_baseline_v1_1_validation.yaml`  
**Script:** `scripts/build_pit_features_sample.py`  
**Validation artifact:** `artifacts/reports/pit_features_baseline_v1_1_validation/p8b1_validation_report.json`（gitignore）

---

## Status

```text
ML-P8B.1: PASS
ML-P8B.2: NOT started
ML-P8B.3 learned model fitting: BLOCKED
Training / model fitting: NOT performed
Formal label_spec.md: UNCHANGED (v1.0.0)
```

---

## Input Dataset

| Field | Value |
|-------|-------|
| source | `artifacts/datasets/pit_sample_baseline_v1_1_validation/` |
| row_count | **1391** |
| sessions | **19** |
| baseline_label_schema_version | `1.1.0-draft` |
| raw lake | `artifacts/raw_lake_sample/` |

---

## Dry-Run Result

```text
input_dataset_exists: true
row_count: 1391 (matches expected)
sessions: 19 (matches expected)
raw_lake_exists: true
dry-run: PASS
```

---

## Smoke Build (2 dates)

| Date | Rows | Leakage | Join |
|------|------|---------|------|
| 2024-01-19 | 77 | PASS | PASS |
| 2024-10-04 | 77 | PASS | PASS |

Smoke total: **154** feature rows — **PASS** before full build.

---

## Full Feature Build (19 sessions)

| Metric | Value |
|--------|-------|
| dates_built | **19 / 19** |
| feature_row_count | **1391** |
| label_row_count | **1391** |
| per-date checkpoint | enabled |
| build duration | ~5.2 h (local) |

All dates completed with per-date leakage **PASS**.

---

## Strict Hash Join

| Metric | Value |
|--------|-------|
| input_dataset_rows | 1391 |
| feature_rows | 1391 |
| joined_rows | 1391 |
| missing_feature_rows | **0** |
| duplicate_feature_keys | **0** |
| join_pass | **true** |

Join keys: `trade_date`, `as_of_timestamp`, `replay_state_hash`, `deterministic_bundle_hash`

---

## Timestamp Leakage Validation

| Metric | Value |
|--------|-------|
| timestamp_leakage_pass | **true** |
| violation_count | **0** |
| max_source_timestamp_delta | null (all `source_timestamp_max <= as_of`) |

---

## Forbidden Input Validation

| Metric | Value |
|--------|-------|
| forbidden_input_pass | **true** |
| forbidden_columns | **[]** |
| failing_row_count | **0** |

Validated via P8B.0 `validate_forbidden_features()` on feature matrix columns. No `labels.*`, `official_close`, or target fields in features.

---

## Feature Coverage / Missingness

| Metric | Value |
|--------|-------|
| feature_column_count | **198** |
| catalog feature groups present | context(9), deterministic(33), chain_summary(20), quote(36), trade(44), greeks(10), index(13), multiresolution(16), quality(12) |
| feature_quality_score mean | ~0.925 |
| nan count (cell-level) | present in sparse window/index features (expected) |
| high_missingness_features | mostly early-session index/multiresolution windows |

Zone-distance features (`distance_spot_to_zone_*`) high missingness (~94%) expected — only ~6.4% anchors have valid zone at as-of.

---

## Run Manifest

| Field | Value |
|-------|-------|
| stage | `ML-P8B.1` |
| model_fitting_allowed | **false** |
| model_type | `feature_dataset_validation_only` |
| leakage_validation_status | **PASS** |
| forbidden_input_validation_status | **PASS** |
| dataset_manifest_hash | `1818cdd2d90433a6` |
| feature_manifest_hash | (see `p8b1_run_manifest.json`) |

Local path: `artifacts/reports/pit_features_baseline_v1_1_validation/p8b1_run_manifest.json`

---

## Artifacts Produced（未提交 git）

```text
artifacts/features/pit_features_baseline_v1_1_validation/
  features.parquet
  manifest.json
  per_date/*.parquet
artifacts/reports/pit_features_baseline_v1_1_validation/
  p8b1_validation_report.json
  p8b1_run_manifest.json
  per_date/*.json
  full_build.log
```

---

## P8B.1 Acceptance Gate

| Gate | Result |
|------|--------|
| feature dataset built for 19 sessions | **PASS** |
| strict hash join PASS | **PASS** |
| timestamp leakage PASS | **PASS** |
| forbidden input PASS | **PASS** |
| coverage report generated | **PASS** |
| run manifest generated | **PASS** |
| no model fitting | **PASS** |
| no model-free baseline eval (P8B.2) | **PASS** (not run) |
| label_spec.md unchanged | **PASS** |
| artifacts not committed | **PASS** |

**ML-P8B.1 overall: PASS**

---

## Implemented Code

| Module | Purpose |
|--------|---------|
| `src/quant_lab/ml/features/p8b1_build.py` | Feature build orchestration from label parquet |
| `src/quant_lab/ml/features/p8b1_validation.py` | Join / leakage / coverage validation |
| `scripts/build_pit_features_sample.py` | CLI entry point |
| `tests/test_p8b1_feature_dataset_validation.py` | Synthetic validation tests |

---

## Next Stage

```text
ML-P8B.2 — Model-Free Baseline Evaluation
```

**ML-P8B.3 learned model fitting remains BLOCKED.**

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial P8B.1 validation report (19-session full build PASS) |

---

**End of report.**
