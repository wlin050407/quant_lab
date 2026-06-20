# Baseline Target Implementation Approval Record

**Phase:** ML-P7.8.1 — Baseline Target Implementation Approval and Label Builder Plan  
**Branch:** `research/zdte-fusion-model`  
**Prior phase:** ML-P7.8 — Baseline Target Coverage Screening (`3810e16`)  
**Evidence:** [`baseline_target_coverage_screening_report.md`](baseline_target_coverage_screening_report.md)  
**Related documents:**

- [`label_spec_addendum_v1_1_proposal.md`](label_spec_addendum_v1_1_proposal.md)
- [`label_target_owner_approval_record.md`](label_target_owner_approval_record.md) (P7.7.2 — screening only)
- [`baseline_label_builder_implementation_plan.md`](baseline_label_builder_implementation_plan.md)
- [`label_schema_v1_1_migration_plan.md`](label_schema_v1_1_migration_plan.md)

---

## Status

```text
Status: Approved for ML-P7.8.2 implementation only
```

This approval **does not** constitute:

- ML-P8B model training
- Formal merge of addendum v1.1 into `docs/ml/label_spec.md`
- Production deployment of new targets
- Replacement of zone labels as official strict primary target
- Modification of Pin Zone thresholds or deterministic financial formulas

**Implementation code is forbidden until ML-P7.8.2.** This document authorizes **planning and additive label builder work only in P7.8.2**, subject to P7.8.2 acceptance gates.

---

## P7.8 Screening Evidence (Gate PASS)

ML-P7.8 baseline coverage screening completed on 19 raw-lake complete dates:

| Metric | Result |
|--------|--------|
| `baseline_eligible_rows` | **1390 / 1391** (99.9%) |
| `eligible_sessions` | **19 / 19** |
| P1 @ 0.25 EM — both classes | **present** (152 near / 1238 not_near; 5 sessions dual-class) |
| P1 @ 0.50 EM — both classes | **present** (317 near / 1073 not_near; 12 sessions dual-class) |
| P2 @ 0.25 / 0.50 EM | **3 classes present** (optional track) |
| Leakage validation | **PASS** (violation_count = 0) |
| Session-grouped split readiness | **PASS** (suggested 11 / 3 / 5 sessions) |
| Zone track (unchanged reference) | included_total = **89** (~6.4%) |

---

## Owner Sign-off

```text
Owner:     Weitong Lin
Date:      2026-06-20
Decision:  Approved for ML-P7.8.2 implementation only
Notes:     P7.8 screening gates passed. Baseline targets are additive.
           Zone labels remain strict secondary. No training in P7.8.2.
           Formal label_spec.md v1.0.0 unchanged until explicit future approval.
```

---

## Approved Scope

The following are **approved** for ML-P7.8.2:

```text
Approved:
- Implement additive baseline targets in screening/dataset label layer.
- Keep existing zone labels unchanged.
- Add label schema version v1.1 draft fields.
- Support P0 regression target: close_distance_to_primary_pin_em.
- Support P1 binary targets for 0.25 EM and 0.50 EM.
- Support optional P2 directional targets for 0.25 EM and 0.50 EM.
- Record target eligibility and exclusion reasons.
- Preserve leakage checks and session-grouped split rules.
- Rebuild dataset for coverage validation only in P7.8.3.
```

### Owner decisions (recorded)

| ID | Decision | Recorded response |
|----|----------|-------------------|
| D1 | Additive baseline targets in label layer | **Approved for P7.8.2 implementation** |
| D2 | P0 `close_distance_to_primary_pin_em` | **Approved** |
| D3 | P1 `close_near_primary_pin` @ 0.25 EM and 0.50 EM | **Approved — both thresholds tracked** |
| D4 | First binary evaluation preference | **0.50 EM preferred** (see below); **0.25 EM not discarded** |
| D5 | P2 `close_above_below_primary_pin` | **Approved as optional additive fields** |
| D6 | Zone labels remain strict secondary | **Approved — unchanged** |
| D7 | ML-P7.8.3 dataset rebuild (coverage validation) | **Approved — no training** |
| D8 | Dual-track baseline + zone inclusion | **Approved** |

### P1 threshold preference (not final production selection)

```text
P1 0.50 EM is preferred for first binary baseline evaluation because screening
showed better class balance (near_ratio 22.8% vs 10.9%) and more sessions with
both classes (12/19 vs 5/19) than 0.25 EM.
```

**0.25 EM remains tracked** for sensitivity analysis. Final production threshold selection requires separate owner approval and, if train-calibrated, training-split-only calibration artifact (see implementation plan).

---

## Not Approved (Explicit)

The following remain **not approved**:

```text
Not approved:
- ML-P8B training.
- Replacing zone label as official strict target.
- Changing Pin Zone thresholds.
- Changing deterministic formulas.
- Using new targets in production.
- Merging addendum v1.1 into docs/ml/label_spec.md (formal v1.1.0) in P7.8.2.
- Full feature build for training purposes.
- Ingest of new trade dates (unless separately authorized).
- Row-level random split for evaluation.
```

---

## Phase Progression

| Phase | Scope | Status |
|-------|-------|--------|
| ML-P7.7.2 | Screening-only approval | Complete |
| ML-P7.8 | Baseline coverage screening | **PASS** |
| **ML-P7.8.1** | Approval + implementation plan (this document) | **Complete** |
| ML-P7.8.2 | Additive label builder code + unit tests | **Next — authorized** |
| ML-P7.8.3 | Dataset rebuild + coverage validation | Authorized after P7.8.2 gates |
| ML-P8B | Model training | **BLOCKED** |

---

## Rollback

If P7.8.2 implementation introduces leakage risk, breaks zone labels, or fails unit tests:

1. Revert label builder changes; zone-only track continues unchanged.
2. v1.0 datasets remain valid; v1.1 draft rows must not enter training without explicit schema handling.
3. This approval remains valid for **re-implementation** after fixes; does not auto-approve ML-P8B.

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-20 | Initial approval for ML-P7.8.2 implementation only (post-P7.8 PASS) |

---

**End of approval record.**
