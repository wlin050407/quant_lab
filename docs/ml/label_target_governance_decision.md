# ML-P7.7 Label Target Governance Decision

**Phase:** ML-P7.7 / ML-P7.7.1 / ML-P7.8 / **ML-P7.8.1**  
**Status:** **Partially approved** — baseline implementation authorized for **ML-P7.8.2 only**  
**Full analysis:** [`label_target_governance_report.md`](label_target_governance_report.md)  
**Addendum draft:** [`label_spec_addendum_v1_1_proposal.md`](label_spec_addendum_v1_1_proposal.md)  
**Owner packet:** [`label_target_owner_review_packet.md`](label_target_owner_review_packet.md)  
**P7.8 screening:** [`baseline_target_coverage_screening_report.md`](baseline_target_coverage_screening_report.md)  
**P7.8.1 approval:** [`baseline_target_implementation_approval.md`](baseline_target_implementation_approval.md)  
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
| ML-P7.8.2 label builder implementation? | **Approved** (additive only) |
| ML-P8B now? | **Forbidden** |

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
4. **ML-P7.8.2** additive label builder + unit tests → **Next**  
5. **ML-P7.8.3** dataset rebuild + coverage validation  
6. Formal `label_spec.md` v1.1.0 merge → **Separate owner approval**  
7. **ML-P8B** → **Blocked** until training explicitly approved  

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
- [ ] ML-P7.8.2 label builder implemented
- [ ] ML-P7.8.3 dataset rebuild validated
- [ ] ML-P8B remains blocked until training explicitly approved

---

## Sparse Zone Root Cause (One Line)

Frozen contract gates (`short_gamma_regime` ~50%, `pin_distance_too_wide` ~37%) — not data gap.

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-06-20 | Initial proposal (P7.7.1) |
| 1.0 | 2026-06-20 | Updated post-P7.8 PASS + P7.8.1 implementation approval |

---

**Status: Approved for ML-P7.8.2 implementation only — ML-P8B blocked**
