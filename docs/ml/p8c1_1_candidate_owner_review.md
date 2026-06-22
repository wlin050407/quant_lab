# ML-P8C.1.1 Candidate List Owner Review

**Date:** 2026-06-22  
**Stage:** ML-P8C.1.1  
**Status:** PASS (owner review only — no ingest / build / fit)  
**Owner:** Weitong Lin  
**Branch:** `research/zdte-fusion-model`  
**Prerequisite:** ML-P8C.1 PASS  

**Sources:**

- [`p8c1_candidate_date_selection_report.md`](p8c1_candidate_date_selection_report.md)
- [`p8c1_ingest_cost_estimate.md`](p8c1_ingest_cost_estimate.md)
- [`p8c2_ingest_owner_approval_gate.md`](p8c2_ingest_owner_approval_gate.md)
- [`p8c_date_selection_rules.md`](p8c_date_selection_rules.md)

**Approval record:** [`p8c2_ingest_owner_approval_record.md`](p8c2_ingest_owner_approval_record.md)

---

## 4.1 Selection Recap

| Field | Value |
|-------|-------|
| `selection_seed` | 20260621 |
| `selection_rules_version` | p8c_date_rules_v1 |
| `existing_sessions` | 19 |
| `candidate_pool` | 605 trading days |
| `selected_new_sessions` | 21 |
| `target_total_sessions` | 40 |
| `forbidden_selection_inputs_used` | false |
| `model_performance_used` | false |
| `target_based_selection_used` | false |
| `actual_ingest_performed` | false |
| `dataset_build_performed` | false |
| `feature_build_performed` | false |
| `model_fitting_performed` | false |

Manifest reference (local, gitignored): `artifacts/reports/p8c_candidate_selection/p8c1_candidate_selection_manifest.json`

---

## 4.2 Frozen Date List

**The P8C Stage 1 selected date list is frozen for P8C.2.**  
**No replacement dates are approved in this owner review.**

| # | `trade_date` | Primary bucket |
|---|--------------|----------------|
| 1 | 2023-02-23 | trend |
| 2 | 2023-03-21 | trend |
| 3 | 2023-05-08 | high_vol |
| 4 | 2023-05-30 | trend |
| 5 | 2023-06-16 | monthly_opex |
| 6 | 2023-06-22 | high_vol |
| 7 | 2023-06-27 | normal_range |
| 8 | 2023-07-03 | early_close |
| 9 | 2023-08-09 | trend |
| 10 | 2023-10-25 | normal_range |
| 11 | 2024-01-03 | normal_range |
| 12 | 2024-02-20 | normal_range |
| 13 | 2024-05-15 | normal_range |
| 14 | 2024-06-06 | normal_range |
| 15 | 2024-10-16 | normal_range |
| 16 | 2024-11-20 | normal_range |
| 17 | 2025-01-17 | monthly_opex |
| 18 | 2025-03-05 | high_vol |
| 19 | 2025-03-25 | high_vol |
| 20 | 2025-05-13 | high_vol |
| 21 | 2025-05-14 | recent |

Existing **19** baseline sessions (P8B.1 cohort) remain frozen and are **not** re-selected or replaced.

---

## 4.3 Bucket Fulfillment Review

| Bucket | Quota | Selected | Status |
|--------|-------|----------|--------|
| normal_range | 8 | 8 | Filled |
| high_vol | 5 | 5 | Filled |
| trend | 4 | 4 | Filled |
| monthly_opex | 2 | 2 | Filled |
| early_close | 1 | 1 | Filled |
| recent | 1 | 1 | Filled |

### Proxy bucket warning

```text
high_vol/trend used deterministic calendar stratification proxy due to missing local index path.
owner_review_recommended = true.
P8C.2/P8C.3 should recheck realized index metrics after ingest/build.
```

Owner accepts proxy tagging for **selection only**. Post-ingest bucket validation is required in P8C.3 reporting — **not** as grounds to replace dates in P8C.2.

---

## 4.4 Temporal Warning Decision

```text
Temporal warning accepted.
min_new_sessions_2024 got 6 vs target 8.
This is accepted without replacing dates, because replacing dates after selection would weaken the frozen pre-declared selection protocol.
The warning must be carried into P8C.2 and P8C.3 reports.
```

```text
This acceptance does not permit performance-based date replacement.
This acceptance does not permit cherry-picking.
```

**Rationale:** P8C.1 selection was deterministic under `selection_seed=20260621` and pre-declared rules. Post-hoc date substitution to satisfy `min_new_sessions_2024` would violate the no-cherry-pick governance in [`p8c_date_selection_rules.md`](p8c_date_selection_rules.md). The 2024 session deficit is documented as a **coverage gap** to monitor in expanded cohort analysis (P8C.3/P8C.5), not as a trigger to alter the frozen list.

---

## 4.5 Cost / Risk Review

| Item | Value |
|------|-------|
| Raw ingest needed | **21 / 21** |
| Raw lake already available | **0 / 21** |
| Estimated runtime (low / base / high) | **504 / 819 / 1302** min |
| Estimated storage (low / base / high) | **8.4 / 16.8 / 31.5** GB |

### Main risks (accepted for P8C.2 planning)

1. **ThetaData latency / rate limits** — 21-day ingest may require batching
2. **High-vol runtime** — proxy-tagged high_vol days may ingest slower
3. **Incomplete partitions** — per-date failure must be recorded without date substitution
4. **Feature build time** — deferred to P8C.3; may dominate total pipeline time
5. **Local disk capacity** — base ~16.8 GB additional raw lake storage

Owner accepts base runtime estimate (~13.7 h) as planning bound, not SLA.

---

## Owner Decision Summary

| Decision | Outcome |
|----------|---------|
| Freeze 21-date list | **Approved** |
| Replace dates for temporal warning | **Rejected** |
| Approve P8C.2 raw lake ingest | **Approved** (see approval record) |
| Approve P8C.3 build in this stage | **Not approved** |
| Approve P8C.4 refit | **Not approved** |
| Approve P8B.4 | **Not approved** |

---

## Compliance (This Stage)

| Item | Status |
|------|--------|
| Actual ingest | **No** |
| Dataset / feature build | **No** |
| Model fitting / `.fit()` | **No** |
| Artifacts committed | **No** |
| `label_spec.md` modified | **No** |
| `requirements.txt` modified | **No** |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial P8C.1.1 owner review (PASS) |
