# ML-P8C.1 Candidate Date Selection Report

**Date:** 2026-06-22  
**Stage:** ML-P8C.1  
**Status:** PASS  
**Branch:** `research/zdte-fusion-model`  
**Selection seed:** `20260621`  
**Rules version:** `p8c_date_rules_v1`

**Sources:** [`p8c_date_selection_rules.md`](p8c_date_selection_rules.md), [`p8c_controlled_dataset_expansion_plan.md`](p8c_controlled_dataset_expansion_plan.md)  
**Manifest (local):** `artifacts/reports/p8c_candidate_selection/p8c1_candidate_selection_manifest.json`

---

## Objective

根据 P8C.0 预声明规则生成 **Stage 1** 扩展候选日期（+21 sessions → 40 total），记录 bucket audit、本地 availability、ingest/build 成本估算。**未** ingest、**未** build、**未** fit。

---

## Selection Rules Recap

| Rule | Value |
|------|-------|
| `selection_seed` | 20260621 |
| Pool window | 2023-01-01 … 2025-06-30 |
| Exclude existing P8B.1 sessions | Yes (19 frozen) |
| Model performance selection | **Forbidden** |
| Target / label selection | **Forbidden** |
| Deterministic bucket fill | Yes (seeded shuffle within bucket) |

**Note:** 对无本地 index path 的候选日，`high_vol` / `trend` 使用 **deterministic calendar stratification proxy**（`sha256(seed:date)`），并标记 `owner_review_recommended=true`。P8C.2 ingest 后应以真实 index 指标复核 bucket 标签。

---

## Existing Sessions Summary

**Count:** 19（P8B.1 baseline validation cohort）

| Split | Sessions |
|-------|----------|
| Train (11) | 2024-01-05 … 2024-10-04 |
| Validation (3) | 2024-11-01, 2024-11-29, 2024-12-06 |
| Test (5) | 2025-01-03 … 2025-05-02 |

所有新选日期与上述 19 日 **无重叠**。

---

## Candidate Pool Summary

| Metric | Value |
|--------|-------|
| Candidate pool size | **605** trading days |
| After excluding existing + known problems | 605 |
| Selected (new) | **21** |
| Target total after Stage 1 | **40** |

---

## Stage 1 Selected Dates (+21)

| # | Date | Primary bucket | Index stats | Owner review |
|---|------|----------------|-------------|--------------|
| 1 | 2023-02-23 | trend | no | recommended |
| 2 | 2023-03-21 | trend | no | recommended |
| 3 | 2023-05-08 | high_vol | no | recommended |
| 4 | 2023-05-30 | trend | no | recommended |
| 5 | 2023-06-16 | monthly_opex | no | no |
| 6 | 2023-06-22 | high_vol | no | recommended |
| 7 | 2023-06-27 | normal_range | no | recommended |
| 8 | 2023-07-03 | early_close | no | no |
| 9 | 2023-08-09 | trend | no | recommended |
| 10 | 2023-10-25 | normal_range | no | recommended |
| 11 | 2024-01-03 | normal_range | no | recommended |
| 12 | 2024-02-20 | normal_range | no | recommended |
| 13 | 2024-05-15 | normal_range | no | recommended |
| 14 | 2024-06-06 | normal_range | no | recommended |
| 15 | 2024-10-16 | normal_range | no | recommended |
| 16 | 2024-11-20 | normal_range | no | recommended |
| 17 | 2025-01-17 | monthly_opex | no | no |
| 18 | 2025-03-05 | high_vol | no | recommended |
| 19 | 2025-03-25 | high_vol | no | recommended |
| 20 | 2025-05-13 | high_vol | no | recommended |
| 21 | 2025-05-14 | recent | no | no |

---

## Bucket Quota Fulfillment

| Bucket | Quota | Selected | Status |
|--------|-------|----------|--------|
| normal_range | 8 | 8 | Filled |
| high_vol | 5 | 5 | Filled |
| trend | 4 | 4 | Filled |
| monthly_opex | 2 | 2 | Filled |
| early_close | 1 | 1 | Filled |
| recent | 1 | 1 | Filled |
| **Total** | **21** | **21** | **PASS** |

---

## Temporal Constraint Warnings

| Warning | Detail |
|---------|--------|
| `min_new_sessions_2024` | got 6, need 8 — **owner review** before P8C.2 |

记录在 manifest `temporal_constraint_warnings`；不触发 performance-based 替换。

---

## Availability Check Summary

| Status | Count |
|--------|-------|
| `raw_lake_status = missing` | 21 / 21 |
| `dataset_status = missing` | 21 / 21 |
| `feature_status = missing` | 21 / 21 |
| `estimated_ingest_needed = true` | 21 |
| `estimated_build_needed = true` | 21 |

**未调用 ThetaData API。** 仅检查本地 partition / shard 存在性。

---

## Cost / Time Estimate Summary

见 [`p8c1_ingest_cost_estimate.md`](p8c1_ingest_cost_estimate.md)。

| Metric | Base estimate |
|--------|---------------|
| Raw lake ingest days | 21 |
| Dataset + feature build days | 21 each |
| Runtime (low / base / high) | 504 / 819 / 1302 minutes |
| Storage (low / base / high) | 8.4 / 16.8 / 31.5 GB |

---

## Forbidden Selection Attestation

```text
forbidden_selection_inputs_used = false
model_performance_used = false
target_based_selection_used = false
actual_ingest_performed = false
dataset_build_performed = false
feature_build_performed = false
model_fitting_performed = false
p8b4_authorized = false
```

---

## Why No Ingest / Build / Fit

P8C.1 scope is **planning and candidate selection only**. Actual ThetaData ingest requires separate **P8C.2 owner approval** — see [`p8c2_ingest_owner_approval_gate.md`](p8c2_ingest_owner_approval_gate.md).

---

## P8C.2 Owner Decision Requirement

Owner must review:

1. Selected 21 dates and bucket assignments (especially proxy-tagged high_vol/trend)
2. Temporal warning for 2024 session count
3. Cost/time estimate
4. Approve or reject **P8C.2 actual ingest** (no date changes without new committed rules)

**P8B.4 remains BLOCKED.**

---

## Execution

```bash
python scripts/select_p8c_candidate_dates.py \
  --config config/ml/p8c_stage1_candidate_selection.yaml \
  --dry-run

python scripts/select_p8c_candidate_dates.py \
  --config config/ml/p8c_stage1_candidate_selection.yaml \
  --execute
```

Both: **PASS**

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial P8C.1 selection report (PASS) |
