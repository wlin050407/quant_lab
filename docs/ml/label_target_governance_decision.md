# ML-P7.7 Label Target Governance Decision

**Phase:** ML-P7.7 / … / ML-P8B.0 / **ML-P8B.1**  
**Status:** **P8B.2 PASS** — **P8B.3 approved (limited simple learned fitting)** — **P8B.4+ blocked**  
**Full analysis:** [`label_target_governance_report.md`](label_target_governance_report.md)  
**Addendum draft:** [`label_spec_addendum_v1_1_proposal.md`](label_spec_addendum_v1_1_proposal.md)  
**Owner packet:** [`label_target_owner_review_packet.md`](label_target_owner_review_packet.md)  
**P7.8 screening:** [`baseline_target_coverage_screening_report.md`](baseline_target_coverage_screening_report.md)  
**P7.8.1 approval:** [`baseline_target_implementation_approval.md`](baseline_target_implementation_approval.md)  
**P7.8.3 validation:** [`baseline_dataset_rebuild_validation_report.md`](baseline_dataset_rebuild_validation_report.md)  
**P7.8.4 gate review:** [`baseline_dataset_gate_review.md`](baseline_dataset_gate_review.md)  
**P8A entry:** [`p8a_entry_approval_record.md`](p8a_entry_approval_record.md)  
**P8A harness:** [`p8a_baseline_modeling_harness_plan.md`](p8a_baseline_modeling_harness_plan.md)  
**P8B gate:** [`p8b_training_gate_proposal.md`](p8b_training_gate_proposal.md)  
**P8B staged approval:** [`p8b_execution_approval_record.md`](p8b_execution_approval_record.md)  
**P8B.3 approval:** [`p8b3_model_fitting_approval_record.md`](p8b3_model_fitting_approval_record.md)  
**P8B.3.0 audit:** [`p8b3_dependency_audit_report.md`](p8b3_dependency_audit_report.md)  
**P8B staged plan:** [`p8b_staged_execution_plan.md`](p8b_staged_execution_plan.md)  
**P8B.0 report:** [`p8b0_modeling_harness_implementation_report.md`](p8b0_modeling_harness_implementation_report.md)  
**P8B.1 report:** [`p8b1_feature_dataset_validation_report.md`](p8b1_feature_dataset_validation_report.md)  
**Implementation plan:** [`baseline_label_builder_implementation_plan.md`](baseline_label_builder_implementation_plan.md)  
**Migration plan:** [`label_schema_v1_1_migration_plan.md`](label_schema_v1_1_migration_plan.md)

---

## Decision Summary

| Question | Decision |
|----------|----------|
| Zone label as sole primary target? | **No** — retain as strict secondary |
| First baseline target? | **Yes** — pin-distance family (addendum v1.1); **P7.8 screening PASS** |
| Modify formal `label_spec.md` now? | **No** — remains v1.0.0; v1.1 draft fields in builder only |
| Modify Pin Zone contract? | **No** (Option D forbidden) |
| Pin-centered fallback zone? | **No** (Option C deferred) |
| ML-P7.8.2 label builder implementation? | **Done — PASS** |
| ML-P7.8.3 dataset rebuild validation? | **Done — PASS** |
| ML-P8A modeling harness plan? | **Done — PASS** (plan only) |
| ML-P8A.1 staged P8B execution approval? | **Done — PASS** (P8B.0–P8B.2) |
| ML-P8B.0 harness implementation? | **Done — PASS** |
| ML-P8B.1 feature dataset validation? | **Done — PASS** |
| P8B.3 learned model fitting? | **Approved (limited scope)** — see [`p8b3_model_fitting_approval_record.md`](p8b3_model_fitting_approval_record.md) |

---

## Evidence Snapshot

### Zone track (P7.6.7)

```text
screened_dates:              19
dates_with_any_zone:         4
dates_with_meaningful_zone:  2  (included >= 10)
included_total:              89
valid_zone_ratio (anchor):   6.4%
negative_dates:              15
```

**Positive dates:** 2024-01-19 (48), 2024-10-04 (39), 2025-05-02 (1), 2025-01-03 (1)

### Baseline track (P7.8 — PASS)

```text
baseline_eligible_rows:      1390 / 1391  (99.9%)
eligible_sessions:           19 / 19
P1 0.25 EM both classes:     yes (5 sessions dual-class)
P1 0.50 EM both classes:     yes (12 sessions dual-class)
leakage:                     PASS
session-grouped split:       PASS (11 / 3 / 5 suggested)
```

---

## Approved Recommendations

### R1 — Zone label role

Keep `close_location_vs_current_zone` as **strict / secondary / Terminal-parity target**. Do not drop zone track.

### R2 — First baseline target

| Priority | Field | Role | Status |
|----------|-------|------|--------|
| P0 | `close_distance_to_primary_pin_em` | Primary regression baseline | **Approved for P7.8.2 impl** |
| P1 | `close_near_primary_pin` @ 0.25 / 0.50 EM | Binary classification | **Approved — 0.50 EM preferred for first eval** |
| P2 | `close_above_below_primary_pin` | Optional ternary | **Approved as optional additive** |

**Baseline inclusion (unchanged from addendum proposal):**

```text
baseline_included when:
  primary_pin_t != null
  AND remaining_expected_move_t finite and > 0
  AND official_close != null
  AND label_source_timestamp > as_of_timestamp
```

Zone inclusion rule **unchanged**.

### R3 — Phase order (updated)

1. ~~Label spec addendum draft~~ → **Done (P7.7.1)**  
2. ~~ML-P7.8 baseline coverage screening~~ → **Done — PASS**  
3. ~~ML-P7.8.1 approval + implementation plan~~ → **Done**  
4. ~~ML-P7.8.2 additive label builder + unit tests~~ → **Done — PASS**  
5. ~~ML-P7.8.3 dataset rebuild + coverage validation~~ → **Done — PASS**  
6. ~~ML-P7.8.4 owner gate review~~ → **Done — PASS**  
7. ~~ML-P8A baseline modeling harness plan~~ → **Done — PASS**  
8. ~~ML-P8A.1 staged P8B execution approval~~ → **Done — PASS**  
9. ~~ML-P8B.0 harness implementation~~ → **Done — PASS**  
10. ~~ML-P8B.1 feature build + join~~ → **Done — PASS**  
11. **ML-P8B.2** model-free baselines → **Next — authorized**  
12. Formal `label_spec.md` v1.1.0 merge → **Separate owner approval**  
13. **ML-P8B.3+** learned fitting / search / production → **Blocked**  

### R4 — Data expansion

Continue raw lake + screening for **zone enrichment only**. Not sole P8B prerequisite. No blind top8 build.

---

## Option Matrix

| Option | Verdict |
|--------|---------|
| A — Expand dates, keep zone primary | Parallel enrichment only |
| B — Add pin-distance baseline | **Approved path — P7.8.2 implementation authorized** |
| C — Fallback zone | Deferred / not recommended |
| D — Change zone thresholds | **Forbidden** without owner |

---

## Sign-off Checklist

- [x] Owner accepts R1–R4 (recorded in [`baseline_target_implementation_approval.md`](baseline_target_implementation_approval.md))
- [x] Baseline near threshold: **both 0.25 / 0.50 EM tracked**; **0.50 EM preferred** for first binary eval
- [x] `label_spec` addendum v1.1 **drafted** (proposal — not merged into formal spec)
- [x] ML-P7.8 scope completed — **PASS**
- [x] ML-P7.8.1 implementation plan approved
- [x] ML-P7.8.2 label builder implemented — **PASS**
- [x] ML-P7.8.3 dataset rebuild validated — **PASS**
- [x] ML-P7.8.4 owner gate review — **PASS**
- [x] ML-P8A entry approved (planning/harness only)
- [x] ML-P8A harness plan written — **PASS**
- [x] ML-P8A.1 staged P8B execution approval — **PASS**
- [x] P8B.0–P8B.2 preparation authorized (see p8b_execution_approval_record.md)
- [x] P8B.0 harness implementation — **PASS**
- [x] P8B.1 feature build + leakage validation — **PASS**
- [x] P8B.2 model-free baseline evaluation — **PASS**
- [x] P8B.3 learned model fitting approval — **Approved (limited scope)**
- [x] P8B.3.0 dependency audit — **PASS** (`importable_but_not_declared`)
- [ ] P8B.3.1 implementation — **Blocked** (owner dependency decision A/B/C)
- [ ] P8B.4+ hyperparameter search / backtest / signals — **Not approved**

---

## Sparse Zone Root Cause (One Line)

Frozen contract gates (`short_gamma_regime` ~50%, `pin_distance_too_wide` ~37%) — not data gap.

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-06-20 | Initial proposal (P7.7.1) |
| 1.0 | 2026-06-20 | Updated post-P7.8 PASS + P7.8.1 implementation approval |
| 1.1 | 2026-06-20 | Updated post-P7.8.3 PASS + P7.8.4 gate review; ML-P8A authorized |
| 1.2 | 2026-06-20 | Updated post-P8A harness plan PASS; P8B gate proposal linked |
| 1.3 | 2026-06-20 | Updated post-P8A.1 staged P8B approval (P8B.0–P8B.2) |
| 1.4 | 2026-06-20 | Updated post-P8B.0 harness implementation PASS |
| 1.5 | 2026-06-21 | Updated post-P8B.1 feature dataset validation PASS |
| 1.6 | 2026-06-21 | Updated post-P8B.2 model-free baseline evaluation PASS |
| 1.7 | 2026-06-21 | P8B.3 limited learned fitting approval |
| 1.8 | 2026-06-21 | P8B.3.0 dependency audit PASS |

---

**Status: ML-P8B.3.0 PASS — P8B.3.1 blocked pending owner dependency decision — P8B.4+ blocked**
