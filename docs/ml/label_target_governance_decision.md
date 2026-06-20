# ML-P7.7 Label Target Governance Decision (Proposal)

**Phase:** ML-P7.7 / ML-P7.7.1  
**Status:** **Pending owner review** — **not approved, not implemented**  
**Full analysis:** [`label_target_governance_report.md`](label_target_governance_report.md)  
**Addendum draft:** [`label_spec_addendum_v1_1_proposal.md`](label_spec_addendum_v1_1_proposal.md)  
**Owner packet:** [`label_target_owner_review_packet.md`](label_target_owner_review_packet.md)

---

## Decision Summary

| Question | Proposal (pending approval) |
|----------|----------------------------|
| Zone label as sole primary target? | **No** — retain as strict secondary |
| First baseline target? | **Yes** — pin-distance family (addendum v1.1 proposal) |
| Modify formal `label_spec.md` now? | **No** — addendum draft only (P7.7.1) |
| Modify Pin Zone contract? | **No** (Option D forbidden) |
| Pin-centered fallback zone? | **No** (Option C deferred) |
| ML-P8B now? | **Forbidden** |

---

## Evidence Snapshot (P7.6.7)

```text
screened_dates:              19
dates_with_any_zone:         4
dates_with_meaningful_zone:  2  (included >= 10)
included_total:              89
valid_zone_ratio (anchor):   6.4%
negative_dates:              15
P8B included gap:            211 (to 300)
```

**Positive dates:** 2024-01-19 (48), 2024-10-04 (39), 2025-05-02 (1), 2025-01-03 (1)

---

## Proposed Recommendations (Not Yet Approved)

### R1 — Zone label role

Keep `close_location_vs_current_zone` as **strict / secondary / Terminal-parity target**. Do not drop zone track.

### R2 — First baseline target (addendum v1.1 proposal)

| Priority | Field | Role |
|----------|-------|------|
| P0 | `close_distance_to_primary_pin_em` | Primary regression baseline |
| P1 | `close_near_primary_pin` | Binary classification (EM threshold governance) |
| P2 | `close_above_below_primary_pin` | Optional ternary (deferrable) |

**Proposed baseline inclusion:**

```text
baseline_included when:
  primary_pin_t != null
  AND remaining_expected_move_t finite and > 0
  AND official_close != null
  AND label_source_timestamp > as_of_timestamp
```

Zone inclusion rule **unchanged**.

### R3 — Next phase order (after owner approval)

1. ~~Label spec addendum draft~~ → **Done (P7.7.1 proposal)**  
2. **ML-P7.8** baseline coverage screening  
3. Formal `label_spec.md` v1.1.0 merge + label builder (future)  
4. **ML-P8B** only after P7.8 gates + implementation  

### R4 — Data expansion

Continue raw lake + screening for **zone enrichment only**. Not sole P8B prerequisite. No blind top8 build.

---

## Option Matrix

| Option | Verdict |
|--------|---------|
| A — Expand dates, keep zone primary | Parallel enrichment only |
| B — Add pin-distance baseline | **Recommended primary path (pending sign-off)** |
| C — Fallback zone | Deferred / not recommended |
| D — Change zone thresholds | **Forbidden** without owner |

---

## Sign-off Checklist

- [ ] Owner accepts R1–R4 ([`label_target_owner_review_packet.md`](label_target_owner_review_packet.md))
- [ ] Baseline near threshold candidate chosen (0.25 EM / 0.50 EM / train-calibrated / defer)
- [x] `label_spec` addendum v1.1 **drafted** (proposal — not merged)
- [ ] ML-P7.8 scope approved
- [ ] ML-P8B remains blocked until baseline coverage gate passes

---

## Sparse Zone Root Cause (One Line)

Frozen contract gates (`short_gamma_regime` ~50%, `pin_distance_too_wide` ~37%) — not data gap.

---

**Status: Pending owner review**
